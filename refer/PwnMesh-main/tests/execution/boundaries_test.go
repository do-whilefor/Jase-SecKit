package execution_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/board/model"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/server"
)

const requestID = "0123456789abcdef0123456789abcdef"

func storeProject(t *testing.T) (*b.Store, b.Graph) {
	t.Helper()
	store, err := b.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := store.Close(); err != nil {
			t.Error(err)
		}
	})
	var graph b.Graph
	err = store.Do(context.Background(), func(tx *b.Tx) error {
		var err error
		graph, err = tx.CreateProject(b.ProjectInput{Title: "Boundary", Origin: "Local fixture", Goal: "Verify bindings"})
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	return store, graph
}

func prepareReason(tx *b.Tx, graph b.Graph, id string) (b.Execution, error) {
	run := b.Execution{ProjectID: graph.Project.ID, ID: id, Namespace: "test", Backend: "docker", Kind: "reason", Lease: "docker@" + id}
	if _, err := tx.ReasonLease(graph.Project.ID, b.LeaseOperation{Op: "claim", Worker: run.Lease, Trigger: "test", Fence: run.Fence()}); err != nil {
		return run, err
	}
	job := protocol.Job{RunID: id, GraphRPC: true, ResultContractVersion: 2, Kind: "reason", WorkerType: "pi", Graph: b.Graph{Project: graph.Project}, Workspace: "/workspace", Budget: model.TaskBudget{MaxIntents: 2}}
	run.Job, _ = json.Marshal(job)
	prepared, err := execution.PrepareRun(tx, run, run.Fence())
	return prepared.Execution, err
}

func TestPreparationRollbackIncludesSnapshotAndLease(t *testing.T) {
	store, graph := storeProject(t)
	abort := errors.New("abort transaction")
	var saved b.Execution
	err := store.Do(context.Background(), func(tx *b.Tx) error {
		var err error
		saved, err = prepareReason(tx, graph, "rollback")
		if err != nil {
			return err
		}
		return abort
	})
	if !errors.Is(err, abort) {
		t.Fatalf("rollback: %v", err)
	}
	var job protocol.Job
	if err := json.Unmarshal(saved.Job, &job); err != nil || job.InputSnapshot == nil {
		t.Fatalf("prepared snapshot: %v", err)
	}
	err = store.View(context.Background(), func(tx *b.Tx) error {
		_, err := tx.Execution(graph.Project.ID, saved.ID)
		assertAPIError(t, err, 404, "Execution not found")
		_, err = tx.InputSnapshotMetadata(graph.Project.ID, job.InputSnapshot.ID)
		assertAPIError(t, err, 404, "Input snapshot not found")
		current, err := tx.Load(graph.Project.ID)
		if err == nil && current.Project.Reason != nil {
			t.Error("rolled-back preparation retained its lease")
		}
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
}

func assertAPIError(t *testing.T, err error, status int, detail string) {
	t.Helper()
	var api *b.APIError
	if !errors.As(err, &api) || api.Status != status || api.Detail != detail {
		t.Fatalf("error = %#v, want %d %q", err, status, detail)
	}
}

func TestExecutionReadHTTPContract(t *testing.T) {
	store, graph := storeProject(t)
	var run b.Execution
	if err := store.Do(context.Background(), func(tx *b.Tx) error { var err error; run, err = prepareReason(tx, graph, "read"); return err }); err != nil {
		t.Fatal(err)
	}
	var job protocol.Job
	if err := json.Unmarshal(run.Job, &job); err != nil {
		t.Fatal(err)
	}
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		_, err := tx.AddProjectHint(graph.Project.ID, b.HintInput{Content: "Later input", Creator: "user"}, "")
		return err
	}); err != nil {
		t.Fatal(err)
	}
	handler := server.NewWithOptions(store, server.Options{})
	request := func(path, body, lease string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
		r.Header.Set("X-PwnMesh-Run", lease)
		r.Header.Set("X-PwnMesh-Lease", "reason")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	path := "/projects/" + graph.Project.ID + "/executions/" + run.ID
	response := request(path+"/input/read", `{"request_id":"0123456789abcdef0123456789abcdef","op":"read_snapshot"}`, run.Lease)
	if response.Code != 200 {
		t.Fatalf("snapshot status %d: %s", response.Code, response.Body)
	}
	var expected any
	if err := store.View(context.Background(), func(tx *b.Tx) error {
		state, err := tx.ReadInputSnapshot(graph.Project.ID, job.InputSnapshot.ID)
		if err != nil {
			return err
		}
		expected, err = protocol.GraphPage(state, protocol.GraphRequest{RequestID: requestID, Op: "read_snapshot"})
		return err
	}); err != nil {
		t.Fatal(err)
	}
	want, _ := json.Marshal(expected)
	if !bytes.Equal(bytes.TrimSpace(response.Body.Bytes()), want) {
		t.Fatalf("snapshot response changed: %s", response.Body)
	}
	for _, test := range []struct {
		route, body, lease, detail string
		status                     int
	}{
		{"/input/read", `{"request_id":"0123456789abcdef0123456789abcdef","op":"read_snapshot"}`, "docker@other", "Snapshot read requires its execution lease", 403},
		{"/updates", `{"request_id":"0123456789abcdef0123456789abcdef","op":"read_updates"}`, run.Lease, "Updates require an active Execute run", 409},
		{"/traces/read", `{"request_id":"0123456789abcdef0123456789abcdef","op":"read_trace_runs"}`, "docker@other", "Trace read requires its execution lease", 403},
	} {
		w := request(path+test.route, test.body, test.lease)
		if w.Code != test.status || !strings.Contains(w.Body.String(), test.detail) {
			t.Errorf("%s: %d %s", test.route, w.Code, w.Body)
		}
	}
}

func TestDecisionAndCurationRequireSnapshotBindings(t *testing.T) {
	graph := b.Graph{Project: b.Project{ID: "p1", Generation: 3, OrchestrationVersion: 1}}
	state := b.State{Graph: graph, Revision: 7}
	version := b.DecisionStateVersion(state)
	snapshot := model.InputSnapshot{Version: 1, ID: strings.Repeat("a", 64), ProjectID: "p1", Generation: 3, StateVersion: version, Revision: 7}
	decision := map[string]any{"kind": "reason", "graph": graph, "input_snapshot": snapshot, "decision": map[string]any{"version": 2, "state_version": version}, "budget": "ignored", "worker_type": 17}
	raw, _ := json.Marshal(decision)
	if got, err := b.DecisionJobVersion(raw); err != nil || got != version {
		t.Fatalf("decision binding: %q %v", got, err)
	}
	decision["state"] = state
	raw, _ = json.Marshal(decision)
	_, err := b.DecisionJobVersion(raw)
	assertAPIError(t, err, 422, "invalid decision snapshot binding")
	delete(decision, "state")
	decision["decision"] = map[string]any{"version": 2, "state_version": version, "closure_protocol": 3}
	raw, _ = json.Marshal(decision)
	_, err = b.DecisionJobVersion(raw)
	assertAPIError(t, err, 422, "unsupported closure protocol")
	curation := map[string]any{"kind": "curate", "graph": graph, "input_snapshot": snapshot, "input_view": map[string]any{"version": 1}, "decision": "ignored", "graph_rpc": "ignored"}
	raw, _ = json.Marshal(curation)
	got, revision, err := b.CurationJobBoundary(raw)
	if err != nil || got != version || revision != 7 {
		t.Fatalf("curation binding: %q %d %v", got, revision, err)
	}
	curation["state"] = state
	raw, _ = json.Marshal(curation)
	_, _, err = b.CurationJobBoundary(raw)
	assertAPIError(t, err, 422, "invalid curation snapshot binding")
	delete(curation, "state")
	delete(curation, "input_snapshot")
	raw, _ = json.Marshal(curation)
	_, _, err = b.CurationJobBoundary(raw)
	assertAPIError(t, err, 422, "invalid curation snapshot binding")
}

func TestSchedulingAdmissionAndGraphReadUseCases(t *testing.T) {
	store, graph := storeProject(t)
	var run b.Execution
	namespace := "test"
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		page, err := execution.Schedule(tx, execution.ScheduleQuery{ProjectID: graph.Project.ID, Namespace: &namespace})
		if err != nil {
			return err
		}
		if page.ProtocolVersion != b.ScheduleProtocolVersion || page.ExecutionChecks["reason:"].Pending {
			t.Errorf("initial scheduling: %+v", page)
		}
		if _, ok := page.ExecutionChecks["reason:"]; !ok {
			t.Error("control admission is missing")
		}
		run, err = prepareReason(tx, graph, "schedule")
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		page, err := execution.Schedule(tx, execution.ScheduleQuery{ProjectID: graph.Project.ID, Namespace: &namespace})
		if err != nil {
			return err
		}
		if !page.ExecutionChecks["reason:"].Pending {
			t.Error("registered decision missing from admission")
		}
		_, err = execution.Schedule(tx, execution.ScheduleQuery{ProjectID: graph.Project.ID, ExpectedVersion: "stale", Namespace: &namespace})
		assertAPIError(t, err, 409, "state_changed: scheduling input changed")
		state, err := tx.State(graph.Project.ID)
		if err != nil {
			return err
		}
		read := protocol.GraphRequest{RequestID: requestID, Op: "read_graph"}
		got, err := execution.ReadGraph(tx, execution.ReadInput{ProjectID: graph.Project.ID, RunID: run.ID, Fence: run.Fence(), Request: read})
		if err != nil {
			return err
		}
		want, err := protocol.GraphPage(state, read)
		if err != nil {
			return err
		}
		gotJSON, _ := json.Marshal(got)
		wantJSON, _ := json.Marshal(want)
		if !bytes.Equal(gotJSON, wantJSON) {
			t.Errorf("graph page changed: %s", gotJSON)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestExecuteUpdatesAndTraceUseCases(t *testing.T) {
	store, graph := storeProject(t)
	var run b.Execution
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		run = b.Execution{ProjectID: graph.Project.ID, ID: "execute", Namespace: "test", Backend: "docker", Kind: "explore", Intent: "i1", Lease: "docker@execute"}
		intent := b.Intent{ID: "i1", From: []string{"origin"}, Description: "Inspect fixture", Creator: "test", Worker: b.Ptr(run.Lease), Heartbeat: b.Ptr(tx.Now), CreatedAt: tx.Now}
		graph.Intents = append(graph.Intents, intent)
		if err := tx.Save(graph); err != nil {
			return err
		}
		job := protocol.Job{RunID: run.ID, GraphRPC: true, ResultContractVersion: 2, Kind: run.Kind, WorkerType: "pi", Graph: b.Graph{Project: graph.Project}, Workspace: "/workspace"}
		run.Job, _ = json.Marshal(job)
		prepared, err := execution.PrepareRun(tx, run, run.Fence())
		run = prepared.Execution
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if err := store.View(context.Background(), func(tx *b.Tx) error {
		input := execution.ReadInput{ProjectID: graph.Project.ID, RunID: run.ID, Fence: run.Fence(), Request: protocol.GraphRequest{RequestID: requestID, Op: "read_updates"}}
		updates, err := execution.ReadUpdates(tx, input)
		if err != nil {
			return err
		}
		if updates.ProjectID != graph.Project.ID || updates.StepID != "i1" || updates.RunID != run.ID || !updates.Complete {
			t.Errorf("updates: %+v", updates)
		}
		cursor := updates.ExecuteUpdateCursor
		cursor.RunID = "other"
		input.Request.Updates = &cursor
		_, err = execution.ReadUpdates(tx, input)
		assertAPIError(t, err, 422, "execution update cursor identity mismatch")
		input.Request = protocol.GraphRequest{RequestID: requestID, Op: "read_trace_runs", Limit: 1}
		traces, err := execution.ReadTraces(tx, input)
		if err != nil {
			return err
		}
		if len(traces.Items) != 1 || traces.Items[0].RunID != run.ID || traces.NextOffset == nil || *traces.NextOffset != 1 {
			t.Errorf("traces: %+v", traces)
		}
		input.Fence.Run = "docker@other"
		_, err = execution.ReadTraces(tx, input)
		assertAPIError(t, err, 403, "Trace read requires its execution lease")
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestSharedJobInputDoesNotRewriteWireIdentity(t *testing.T) {
	state := model.State{Graph: model.Graph{Project: model.Project{ID: "p1", Generation: 2}}, Revision: 8}
	job := protocol.Job{Kind: "curate", Graph: state.Graph, InputSnapshot: &model.InputSnapshot{Version: 1, ID: strings.Repeat("b", 64), ProjectID: "p1", Generation: 2, StateVersion: strings.Repeat("a", 64), Revision: 11}}
	before, _ := json.Marshal(job)
	if job.CurationVersion() != job.InputSnapshot.StateVersion || job.CurationRevision() != 11 {
		t.Fatal("snapshot boundary differs")
	}
	after, _ := json.Marshal(job)
	if !bytes.Equal(before, after) {
		t.Fatal("reading a binding changed the job")
	}
	var binding model.CurationJobBinding
	if err := json.Unmarshal(after, &binding); err != nil {
		t.Fatal(err)
	}
	if binding.StateVersion() != job.CurationVersion() || binding.Revision() != job.CurationRevision() {
		t.Fatal("Board and protocol input boundaries differ")
	}
	job.InputSnapshot, job.State = nil, &state
	before, _ = json.Marshal(job)
	if job.CurationVersion() != "" || job.CurationRevision() != 0 {
		t.Fatal("inline state fabricated an input boundary")
	}
	after, _ = json.Marshal(job)
	if !bytes.Equal(before, after) {
		t.Fatal("reading an unsupported binding changed the job")
	}
	binding = model.CurationJobBinding{}
	if err := json.Unmarshal(after, &binding); err != nil {
		t.Fatal(err)
	}
	if binding.StateVersion() != "" || binding.Revision() != 0 {
		t.Fatal("Board inferred an unsupported inline boundary")
	}
}

func TestStateProjectionsRequireExplicitMetadata(t *testing.T) {
	state := model.State{Graph: model.Graph{
		Project: model.Project{ID: "p1", OrchestrationVersion: 1},
		Facts:   []model.Fact{{ID: "origin", Description: "input"}, {ID: "goal", Description: "goal"}, {ID: "f1", Description: "observation"}},
		Intents: []model.Intent{{ID: "s1", Description: "Inspect fixture", To: model.Ptr("f1")}},
	}}
	if _, err := model.ContextView(state, "", 0); err == nil || !strings.Contains(err.Error(), "missing goal") {
		t.Fatalf("missing goal was inferred: %v", err)
	}
	if len(state.History()) != 0 || len(model.RankRelatedFacts(state, model.RelatedQuery{IDs: []string{"f1"}})) != 0 {
		t.Fatal("graph records were promoted into state metadata")
	}
	for _, section := range []string{"facts", "goals", "steps"} {
		page, err := protocol.GraphPage(state, protocol.GraphRequest{Op: "read_graph", Section: section})
		if err != nil {
			t.Fatal(err)
		}
		raw, _ := json.Marshal(page)
		var result struct {
			Items []json.RawMessage `json:"items"`
		}
		if err := json.Unmarshal(raw, &result); err != nil || len(result.Items) != 0 {
			t.Fatalf("%s fabricated metadata: %s %v", section, raw, err)
		}
	}
	state.Goals = []model.Goal{{ID: "goal", Condition: "goal", Status: "open"}}
	state.Steps = []model.Step{{ID: "s1", GoalID: "goal", Description: "Inspect fixture", Status: "completed", Result: model.Ptr("f1"), SupportValid: true}}
	state.FactRecords = []model.FactRecord{{ID: "f1", Description: "observation", Status: "valid", SourceStepID: "s1"}}
	if _, err := model.ContextView(state, "s1", 0); err != nil {
		t.Fatalf("explicit state metadata: %v", err)
	}
	history := state.History()
	if len(history) != 1 || len(history[0].Members) != 2 || history[0].Members[1].ID != "f1" {
		t.Fatalf("explicit provenance was not retained: %+v", history)
	}
	state.FactRecords[0].SourceStepID = ""
	history = state.History()
	if len(history) != 1 || len(history[0].Members) != 1 {
		t.Fatalf("step result fabricated fact provenance: %+v", history)
	}
}

func TestUnregisteredReasonLeaseCannotAuthorizeWrites(t *testing.T) {
	store, graph := storeProject(t)
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		fence := b.ExecutionFence{Run: "docker@unregistered", Lease: "reason"}
		if _, err := tx.ReasonLease(graph.Project.ID, b.LeaseOperation{Op: "claim", Worker: fence.Run, Trigger: "test", Fence: fence}); err != nil {
			return err
		}
		state, err := tx.State(graph.Project.ID)
		if err != nil {
			return err
		}
		assertAPIError(t, tx.CheckNewStepLimit(graph.Project.ID, fence.Run), 403, "decision requires a registered input snapshot")
		assertAPIError(t, tx.CheckDecisionStateVersion(state, fence, b.DecisionStateVersion(state)), 403, "decision requires a registered input snapshot")
		_, err = tx.DecisionReadState(state, fence, false)
		assertAPIError(t, err, 403, "decision requires a registered input snapshot")
		_, err = tx.StateAction(graph.Project.ID, fence, b.StateAction{Op: "step", IdempotencyKey: "unregistered-step", ExpectedVersion: b.DecisionStateVersion(state), Payload: json.RawMessage(`{"op":"create","goal_id":"goal","description":"Inspect fixture","from":["origin"]}`)})
		assertAPIError(t, err, 403, "Decide must submit its plan through a decision batch")
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}
