package dispatcher

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"sort"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/dispatchrun"
	"pwnmesh/internal/protocol"
)

func digest(v any) string {
	raw, _ := json.Marshal(v)
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

func (s *Scheduler) namespace() string {
	if s.Config.Container.Namespace == "" {
		return "pwnmesh"
	}
	return s.Config.Container.Namespace
}

func (s *Scheduler) environmentID(w config.Worker) string {
	tools, err := w.ToolEnvironment()
	if err != nil {
		return "" // Invalid environments cannot be admitted or recovered.
	}
	// Provider credentials rotate independently. Tool configuration is part of
	// the assignment, including explicit empty overrides of image defaults.
	env := map[string]string{}
	for _, key := range []string{"PWNMESH_REASONING_EFFORT", "PWNMESH_MAX_OUTPUT_TOKENS", "PWNMESH_CONTEXT_BYTES", "PWNMESH_REQUEST_TIMEOUT"} {
		env[key] = w.Env[key]
	}
	protocol := w.Env["PWNMESH_MODEL_PROTOCOL"]
	if protocol == "" || protocol == "anthropic" {
		if mode := w.Env["ANTHROPIC_AUTH_MODE"]; mode != "" && mode != "api_key" {
			env["ANTHROPIC_AUTH_MODE"] = mode
		}
		// Keep existing Anthropic identities stable when its default becomes explicit.
		for _, key := range []string{"ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL"} {
			env[key] = w.Env[key]
		}
	} else if protocol == "openai" {
		env["PWNMESH_MODEL_PROTOCOL"] = protocol
		env["OPENAI_BASE_URL"], env["OPENAI_MODEL"] = w.Env["OPENAI_BASE_URL"], w.Env["OPENAI_MODEL"]
	} else {
		return ""
	}
	// Pi identity and tool values fence continuation; saved results bypass it.
	return digest(struct {
		Version int
		Type    string
		Image   string
		Network string
		Caps    []string
		Env     map[string]string
		Tools   map[string]string
	}{2, "pi", s.Config.Container.Image, s.Config.Container.Network, s.Config.Container.CapAdd, env, tools})
}

func (s *Scheduler) releaseIdleAdmissions() {
	for project := range s.admitted {
		busy := false
		for _, t := range s.runs.Running() {
			if t.ProjectID == project {
				busy = true
				break
			}
		}
		if !busy {
			delete(s.admitted, project)
		}
	}
}

// Admission checks must belong to the same snapshot as the scheduling input.
func candidateCheck(input board.SchedulePage, kind, intent string) (board.ExecutionCheck, error) {
	key := kind + ":" + intent
	if check, ok := input.ExecutionChecks[key]; ok {
		return check, nil
	}
	return board.ExecutionCheck{}, fmt.Errorf("scheduling response missing execution check %q", key)
}

func (s *Scheduler) restoreDecisionBoundary(project string, latest *board.ExecutionSummary) {
	if latest == nil || latest.Generation != s.generations[project] {
		return
	}
	s.checkpoints[project] = checkpoint{latest.FactCount, latest.HintCount, latest.OpenCount}
	s.decisionRevisions[project] = latest.DecisionRevision
}

func (s *Scheduler) loadExecutions(ctx context.Context) error {
	s.pendingExecutions = nil
	var after int64
	for {
		page, err := s.Client.PendingExecutions(ctx, s.namespace(), after)
		if err != nil {
			return err
		}
		s.pendingExecutions = append(s.pendingExecutions, page.Items...)
		if page.NextCursor == 0 {
			return nil
		}
		if page.NextCursor <= after {
			return errors.New("execution pending cursor did not advance")
		}
		after = page.NextCursor
	}
}

func (s *Scheduler) recoverExecutions(ctx context.Context, states map[string]string) error {
	for run, until := range s.deliveryWaits {
		if !time.Now().Before(until) {
			delete(s.deliveryWaits, run)
		}
	}
	// Resume control work before producers after a dispatcher restart. No
	// business plan is changed; these are already registered executions.
	sort.SliceStable(s.pendingExecutions, func(i, j int) bool {
		control := func(kind string) bool { return kind == "reason" || kind == "curate" }
		return control(s.pendingExecutions[i].Kind) && !control(s.pendingExecutions[j].Kind)
	})
	for _, e := range s.pendingExecutions {
		if !e.Pending() || s.runs.Has(e.ID) || !slices.Contains([]string{"reason", "curate", "explore"}, e.Kind) {
			continue
		}
		project := board.Project{ID: e.ProjectID, Generation: e.Generation}
		t := &dispatchrun.Assignment{Job: protocol.Job{RunID: e.ID, Graph: board.Graph{Project: project}}, Lease: Lease{Run: e.Lease, Kind: e.Kind, Intent: e.Intent}}
		if states[e.ProjectID] != "active" || e.Generation != s.generations[e.ProjectID] {
			s.runs.Terminal(*t, "cancelled", protocol.Result{Status: "failed", FailureKind: "hard_cancelled", Error: "project is not active"})
			continue
		}
		if s.modelSettingsErr != nil && e.Status != "result_pending" {
			continue
		}
		if until, waiting := s.deliveryWaits[e.ID]; waiting {
			s.wakeAt(until)
			continue
		}
		if !s.runs.RestartReady(ctx, project) {
			continue
		}
		if s.runs.Count() >= s.Config.Runtime.MaxWorkers {
			break
		}
		if !s.admitted[e.ProjectID] && len(s.admitted) >= s.Config.Runtime.MaxProjects {
			continue
		}
		projectCount, backendCount := 0, 0
		staleRound := false
		for _, running := range s.runs.Running() {
			if running.ProjectID == e.ProjectID {
				projectCount++
				staleRound = staleRound || running.Generation != e.Generation
			}
			if running.Backend == e.Backend {
				backendCount++
			}
		}
		if staleRound || projectCount >= s.Config.Runtime.MaxProjectWorkers {
			continue
		}
		saved, err := s.runs.Load(ctx, e)
		if err != nil {
			var pe *ProtocolError
			if errors.As(err, &pe) && pe.Status == 404 {
				continue
			}
			return err
		}
		*t = saved
		if !t.Execution.Pending() || t.Job.Graph.Project.OrchestrationVersion != 1 || !t.Job.GraphRPC || t.Job.ResultContractVersion != 2 {
			continue
		}
		// A saved result only needs its registered lease and input fences. Its
		// original model/backend may have been removed since execution finished.
		t.Worker.Name = e.Backend
		if t.Execution.Status != "result_pending" {
			for _, w := range s.Config.Workers {
				if w.Name == e.Backend {
					t.Worker = w
					break
				}
			}
			environment := s.environmentID(t.Worker)
			if t.Job.WorkerType != "pi" || !slices.Contains(t.Worker.TaskTypes, e.Kind) || environment == "" || t.Job.EnvironmentID != environment {
				s.runs.Terminal(*t, "failed", protocol.Result{Status: "failed", FailureKind: "configuration", Error: "registered execution environment changed"})
				continue
			}
			if backendCount >= t.Worker.MaxRunning || e.Kind == "explore" && (!s.executionCapacity(e.ProjectID) || !s.backendExecutionCapacity(t.Worker.Name, t.Worker.MaxRunning)) {
				continue
			}
		}
		// Readiness only gates model work. Results already accepted by the
		// server can finish delivery even while this backend is unavailable.
		until := s.unhealthy[t.Worker.Name]
		if t.Execution.Status != "result_pending" && (s.incompatible[t.Worker.Name] != "" || time.Now().Before(until)) {
			if s.incompatible[t.Worker.Name] == "" {
				s.wakeAt(until)
			}
			continue
		}
		err = s.runs.Resume(ctx, *t)
		if err != nil {
			var pe *ProtocolError
			if errors.As(err, &pe) && (pe.Status == 403 || pe.Status == 404 || pe.Status == 409) {
				failure := "session_invalid"
				var rpcFailure *protocol.RPCError
				if errors.As(err, &rpcFailure) && rpcFailure.Status == 409 && rpcFailure.Code == board.CodeRecoveryExhausted {
					failure = "recovery_exhausted"
				}
				s.runs.Terminal(*t, "failed", protocol.Result{Status: "failed", FailureKind: failure, Error: err.Error()})
				continue
			}
			return err
		}
		s.admitted[e.ProjectID] = true
	}
	return nil
}
