//go:build linux

package worker_test

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"pwnmesh/internal/agent"
	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/worker"
	"pwnmesh/internal/worker/dag"
	"pwnmesh/internal/workergraph"
)

func TestWorkerRejectsInlineInputBeforeExecution(t *testing.T) {
	job := snapshotJob(t.TempDir())
	job.InputSnapshot, job.InputView = nil, nil
	job.Graph.Intents = []board.Intent{*job.Intent}
	runDir := filepath.Join(job.Workspace, "run")
	_, err := worker.Run(context.Background(), job, worker.Options{RunDir: runDir})
	if err == nil || !strings.Contains(err.Error(), "immutable input snapshot") {
		t.Fatalf("inline input was not rejected: %v", err)
	}
	if _, err := worker.Prompt(job, false); err == nil {
		t.Fatal("prompt rebuilt a retired inline input")
	}
	if _, err := os.Stat(runDir); !os.IsNotExist(err) {
		t.Fatal("rejected input created execution state")
	}
}

func TestWorkerRequiresPiExecutionIdentity(t *testing.T) {
	for _, backend := range []string{"", "go"} {
		t.Run(backend, func(t *testing.T) {
			job := snapshotJob(t.TempDir())
			job.WorkerType = backend
			runDir := filepath.Join(job.Workspace, "run")
			_, err := worker.Run(context.Background(), job, worker.Options{RunDir: runDir})
			if err == nil || !strings.Contains(err.Error(), "requires the pi backend") {
				t.Fatalf("retired backend was not rejected: %v", err)
			}
			if _, err := os.Stat(runDir); !os.IsNotExist(err) {
				t.Fatal("rejected backend created execution state")
			}
		})
	}
}

func TestWorkerRejectsRetiredSessionSchemasWithoutChangingBytes(t *testing.T) {
	for _, version := range []int{0, 1, 2, 3} {
		t.Run(fmt.Sprint(version), func(t *testing.T) {
			job := snapshotJob(t.TempDir())
			runDir := filepath.Join(job.Workspace, "run")
			if err := os.MkdirAll(runDir, 0700); err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(runDir, "session.json")
			original := []byte(fmt.Sprintf(`{"schema_version":%d,"history":[{"role":"user","content":[{"type":"text","text":"retained old work"}]}]}`, version))
			if err := os.WriteFile(path, original, 0600); err != nil {
				t.Fatal(err)
			}
			calls := 0
			provider := recoveryProvider(func([]agent.Message) (agent.Message, error) {
				calls++
				return agent.Message{}, errors.New("unexpected provider call")
			})
			_, err := worker.Run(context.Background(), job, worker.Options{RunDir: runDir, Provider: provider})
			if err == nil || !strings.Contains(err.Error(), "unsupported session schema_version") || calls != 0 {
				t.Fatalf("retired session was not rejected before model execution: calls=%d error=%v", calls, err)
			}
			retained, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(retained, original) {
				t.Fatalf("rejected session bytes changed: %v", err)
			}
		})
	}
}

func TestDecisionRecoveryChecksReceiptBeforeRejectingRetiredConflict(t *testing.T) {
	for _, committed := range []bool{false, true} {
		t.Run(fmt.Sprint(committed), func(t *testing.T) {
			job := snapshotJob(t.TempDir())
			job.Kind, job.Intent = "reason", nil
			job.Decision = &board.DecisionContext{Version: 2, StateVersion: job.InputSnapshot.StateVersion,
				Generation: job.InputSnapshot.Generation, ToRevision: job.InputSnapshot.Revision, View: job.InputView}
			job.InputView = nil
			runDir := filepath.Join(job.Workspace, "run")
			writeBoundSession(t, job, runDir, map[string]any{
				"decision_conflict": "state_changed: retained terminal planner conflict",
			})
			receipts, calls := 0, 0
			output := &recoveryOutput{runDir: runDir, graph: func(request protocol.GraphRequest) protocol.GraphResponse {
				if request.Op != "decision_receipt" {
					t.Errorf("unexpected request: %s", request.Op)
				}
				receipts++
				raw, _ := json.Marshal(board.DecisionReceipt{Committed: committed, StateVersion: job.Decision.StateVersion})
				return protocol.GraphResponse{Result: raw}
			}}
			provider := recoveryProvider(func([]agent.Message) (agent.Message, error) {
				calls++
				return agent.Message{}, errors.New("unexpected provider call")
			})
			result, err := worker.Run(context.Background(), job, worker.Options{RunDir: runDir, Provider: provider, Output: output})
			if receipts != 1 || calls != 0 {
				t.Fatalf("recovery bypassed receipt authority: receipts=%d model_calls=%d error=%v", receipts, calls, err)
			}
			if committed {
				if err != nil || result.Status != "success" {
					t.Fatalf("committed receipt lost authority: %+v %v", result, err)
				}
			} else if err == nil || !strings.Contains(err.Error(), "unsupported saved decision conflict") {
				t.Fatalf("uncommitted old conflict was silently adapted: %v", err)
			}
		})
	}
}

func writeBoundSession(t *testing.T, job worker.Job, runDir string, fields map[string]any) []byte {
	t.Helper()
	if err := os.MkdirAll(runDir, 0700); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(job)
	if err != nil {
		t.Fatal(err)
	}
	digest, empty := sha256.Sum256(raw), sha256.Sum256(nil)
	identity := map[string]any{
		"project_id": job.Graph.Project.ID, "run_id": job.RunID, "kind": job.Kind,
		"workspace": job.Workspace, "workspace_target": job.Workspace,
		"run_dir": runDir, "run_dir_target": runDir,
		"job_digest": hex.EncodeToString(digest[:]), "original_budget": job.Budget,
	}
	if job.Intent != nil {
		identity["step_id"] = job.Intent.ID
	}
	state := map[string]any{
		"schema_version": 4, "run_id": job.RunID, "kind": job.Kind, "started_at": time.Now(),
		"log_checkpoint": map[string]any{"offset": 0, "sha256": hex.EncodeToString(empty[:])},
		"identity":       identity,
	}
	for key, value := range fields {
		state[key] = value
	}
	raw, err = json.Marshal(state)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(runDir, "session.json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestWorkerRejectsMalformedSavedSuccessWithoutReplay(t *testing.T) {
	for _, test := range []struct {
		name, text, stop string
		retryable        bool
		valid            bool
	}{
		{name: "invalid", text: "not a structured result", stop: "end_turn"},
		{name: "continue", text: `{"accepted":true,"outcome":"continue","reason":"More work remains."}`, stop: "end_turn"},
		{name: "incomplete", text: `{"accepted":true,"outcome":"incomplete","reason":"No result was established."}`, stop: "end_turn"},
		{name: "truncated", text: `{"accepted":false,"reason":"The task is outside the supplied scope."}`, stop: "max_tokens"},
		{name: "retryable", text: `{"accepted":false,"reason":"The task is outside the supplied scope."}`, stop: "end_turn", retryable: true},
		{name: "valid", text: `{"accepted":false,"reason":"The task is outside the supplied scope."}`, stop: "end_turn", valid: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			job := snapshotJob(t.TempDir())
			runDir := filepath.Join(job.Workspace, ".pwnmesh", "runs", job.RunID)
			assistant := agent.Text("assistant", test.text)
			assistant.StopReason = test.stop
			input, err := json.Marshal(map[string]any{"cwd": job.Workspace, "sessionPath": filepath.Join(runDir, "pi-session.jsonl"),
				"messages": []agent.Message{agent.Text("user", "Inspect the assigned local inputs."), assistant}})
			if err != nil {
				t.Fatal(err)
			}
			command := exec.CommandContext(ctx, "node", filepath.Join("..", "pi", "session-fixture.mjs"))
			command.Stdin = bytes.NewReader(input)
			snapshot, err := command.Output()
			if err != nil {
				t.Fatalf("seed canonical Pi transcript: %v", err)
			}
			original := writeBoundSession(t, job, runDir, map[string]any{
				"result":             worker.Result{Type: "result", Status: "success", Text: test.text, Retryable: test.retryable},
				"context_checkpoint": agent.ContextCheckpoint{Version: agent.ContextCheckpointVersion, LastSequence: 2, PiSession: snapshot},
			})
			calls := 0
			provider := recoveryProvider(func([]agent.Message) (agent.Message, error) {
				calls++
				return agent.Message{}, &agent.ModelError{Kind: agent.ErrorTransport, Err: errors.New("unexpected replay")}
			})
			result, err := worker.Run(ctx, job, worker.Options{RunDir: runDir, Provider: provider, Output: &recoveryOutput{runDir: runDir}})
			if test.valid {
				if err != nil || result.Status != "success" || result.Text != test.text || calls != 0 {
					t.Errorf("valid terminal success was not retained: result=%+v calls=%d error=%v", result, calls, err)
				}
			} else if err == nil || !strings.Contains(err.Error(), "invalid saved successful result") || calls != 0 {
				t.Errorf("malformed success was not rejected before replay: calls=%d error=%v", calls, err)
			}
			retained, err := os.ReadFile(filepath.Join(runDir, "session.json"))
			if err != nil || !bytes.Equal(retained, original) {
				t.Errorf("malformed success was rewritten: %v", err)
			}
		})
	}
}

func TestDAGRejectsReuseWithoutOriginalExecutionWindow(t *testing.T) {
	workspace := t.TempDir()
	runDir := filepath.Join(workspace, "run")
	if err := os.MkdirAll(runDir, 0700); err != nil {
		t.Fatal(err)
	}
	scope := dag.Scope{RunID: "run", RunDir: runDir, Workspace: workspace,
		Identity: func(string) (json.RawMessage, error) { return json.RawMessage(`{"run_id":"run"}`), nil }}
	source := json.RawMessage(`{"key":"source","nodes":[{"id":"observe","command":"printf x >> count; printf observed","resources":[]}]}`)
	target := json.RawMessage(`{"key":"target","nodes":[{"id":"retained","kind":"reuse","reuse_from":{"key":"source","node":"observe"},"resources":[]}]}`)
	for _, spec := range []json.RawMessage{source, target} {
		if _, err := dag.Run(context.Background(), scope, spec, nil); err != nil {
			t.Fatal(err)
		}
	}
	dir := filepath.Join(runDir, "graph-tools", "target")
	checkpoint, err := workergraph.ReadCheckpoint(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}
	var value dag.Output
	if err := json.Unmarshal(checkpoint.Nodes[0].Output.Value, &value); err != nil {
		t.Fatal(err)
	}
	if value.ReusedFrom == nil || value.ReusedFrom.ExecutionStartedAt == "" || value.ReusedFrom.ExecutionFinishedAt == "" {
		t.Fatal("current reuse receipt lacks its original execution window")
	}
	value.ReusedFrom.ExecutionStartedAt, value.ReusedFrom.ExecutionFinishedAt = "", ""
	checkpoint.Nodes[0].Output.Value, err = json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(checkpoint)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "graph.json")
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := dag.Run(context.Background(), scope, target, nil); err == nil || !strings.Contains(err.Error(), "provenance changed") {
		t.Fatalf("retired reuse receipt was not rejected: %v", err)
	}
	retained, err := workergraph.ReadCheckpoint(context.Background(), dir)
	if err != nil || len(retained.Nodes) != 1 || !bytes.Equal(retained.Nodes[0].Output.Value, checkpoint.Nodes[0].Output.Value) {
		t.Fatalf("rejected graph provenance was changed: %v", err)
	}
	countPath := filepath.Join(runDir, "graph-tools", "source", "nodes", "observe", "count")
	if count, err := os.ReadFile(countPath); err != nil || string(count) != "x" {
		t.Fatalf("source effects replayed: count=%q error=%v", count, err)
	}
}

func TestDAGRejectsRuntimeFilesAsArtifacts(t *testing.T) {
	for _, artifact := range []string{"session.json", "events.jsonl", "pi-session.jsonl"} {
		t.Run(artifact, func(t *testing.T) {
			workspace := t.TempDir()
			runDir := filepath.Join(workspace, "run")
			if err := os.MkdirAll(runDir, 0700); err != nil {
				t.Fatal(err)
			}
			scope := dag.Scope{RunID: "run", RunDir: runDir, Workspace: workspace,
				Identity: func(string) (json.RawMessage, error) { return json.RawMessage(`{"run_id":"run"}`), nil }}
			spec, err := json.Marshal(dag.Spec{Key: "reserved", Nodes: []dag.Node{{
				ID: "child", Kind: "agent", Task: "Inspect local inputs.", Resources: []string{}, Artifacts: []string{artifact},
			}}})
			if err != nil {
				t.Fatal(err)
			}
			if _, err := dag.Run(context.Background(), scope, spec, nil); err == nil || !strings.Contains(err.Error(), "artifacts must be clean relative paths") {
				t.Fatalf("runtime file accepted as an artifact: %v", err)
			}
			if _, err := os.Stat(filepath.Join(runDir, "graph-tools")); !os.IsNotExist(err) {
				t.Fatal("rejected artifact declaration created graph execution state")
			}
		})
	}
}
