package dispatcher_test

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"testing"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/dispatcher"
	"pwnmesh/internal/protocol"
)

type schedulingServer struct {
	controlclient.Server
	events  *[]string
	failure error
}

func (s schedulingServer) Settings(context.Context) (board.Settings, error) {
	*s.events = append(*s.events, "settings")
	return board.Settings{IntentTimeout: 30, ReasonTimeout: 30}, nil
}
func (s schedulingServer) List(context.Context) ([]board.Summary, error) {
	*s.events = append(*s.events, "projects")
	return []board.Summary{{Project: board.Project{ID: "project", Status: "active", OrchestrationVersion: 1}}}, nil
}
func (s schedulingServer) PendingExecutions(context.Context, string, int64) (board.ExecutionPage, error) {
	*s.events = append(*s.events, "recover")
	return board.ExecutionPage{}, s.failure
}
func (s schedulingServer) Schedule(context.Context, string, controlclient.ScheduleQuery) (board.SchedulePage, error) {
	*s.events = append(*s.events, "schedule")
	return board.SchedulePage{}, nil
}

type idleRunner struct{ events *[]string }

func (r idleRunner) Projects(context.Context) ([]string, error) {
	*r.events = append(*r.events, "cleanup")
	return nil, nil
}
func (r idleRunner) Cleanup(context.Context, string, string) error { return nil }
func (r idleRunner) Run(context.Context, config.Worker, protocol.Job) (protocol.Result, error) {
	return protocol.Result{}, errors.New("unexpected launch")
}

func TestRecoveryPrecedesAdmissionThroughTypedControlPlane(t *testing.T) {
	for _, broken := range []bool{false, true} {
		t.Run(map[bool]string{false: "healthy", true: "recovery unavailable"}[broken], func(t *testing.T) {
			events := []string{}
			failure := errors.New("recovery unavailable")
			server := schedulingServer{events: &events}
			if broken {
				server.failure = failure
			}
			scheduler := dispatcher.New(config.Config{Runtime: config.Runtime{Interval: 1, MaxWorkers: 1, MaxProjects: 1, MaxProjectWorkers: 1}}, idleRunner{events: &events})
			scheduler.Client = server
			err := scheduler.Step(context.Background())
			want := []string{"settings", "projects", "recover", "cleanup", "schedule"}
			if broken {
				want = want[:3]
				if !errors.Is(err, failure) {
					t.Fatalf("error = %v", err)
				}
			} else if err != nil {
				t.Fatal(err)
			}
			if !reflect.DeepEqual(events, want) {
				t.Fatalf("events=%v, want=%v", events, want)
			}
		})
	}
}

type pendingResultServer struct {
	controlclient.Server
	execution board.Execution
	released  chan struct{}
	applied   bool
}

func (s *pendingResultServer) Settings(context.Context) (board.Settings, error) {
	return board.Settings{IntentTimeout: 30, ReasonTimeout: 30}, nil
}
func (s *pendingResultServer) List(context.Context) ([]board.Summary, error) {
	return []board.Summary{{Project: board.Project{ID: "project", Status: "active", OrchestrationVersion: 1}}}, nil
}
func (s *pendingResultServer) PendingExecutions(context.Context, string, int64) (board.ExecutionPage, error) {
	return board.ExecutionPage{Items: []board.ExecutionSummary{{ProjectID: "project", ID: "run", Backend: "removed-worker", Kind: "explore", Intent: "step", Lease: "removed-worker@run", Status: "result_pending"}}}, nil
}
func (s *pendingResultServer) Execution(context.Context, string, string, string) (board.Execution, error) {
	return s.execution, nil
}
func (s *pendingResultServer) Resume(context.Context, string, string, controlclient.Lease) (board.Execution, error) {
	return s.execution, nil
}
func (s *pendingResultServer) Apply(context.Context, string, string, controlclient.Lease) (string, error) {
	s.applied = true
	return "succeeded", nil
}
func (s *pendingResultServer) Release(context.Context, string, controlclient.Lease) error {
	close(s.released)
	return nil
}

type forbiddenRunner struct {
	started chan struct{}
}

func (r forbiddenRunner) Projects(context.Context) ([]string, error)    { return nil, nil }
func (r forbiddenRunner) Cleanup(context.Context, string, string) error { return nil }
func (r forbiddenRunner) Run(context.Context, config.Worker, protocol.Job) (protocol.Result, error) {
	close(r.started)
	return protocol.Result{}, errors.New("saved result must not replay work")
}

func TestSavedResultSettlesWithoutOriginalWorker(t *testing.T) {
	job, err := json.Marshal(protocol.Job{RunID: "run", Kind: "explore", GraphRPC: true, ResultContractVersion: 2, Graph: board.Graph{Project: board.Project{ID: "project", Status: "active", OrchestrationVersion: 1}}, Intent: &board.Intent{ID: "step"}})
	if err != nil {
		t.Fatal(err)
	}
	server := &pendingResultServer{execution: board.Execution{ProjectID: "project", ID: "run", Backend: "removed-worker", Kind: "explore", Intent: "step", Lease: "removed-worker@run", Status: "result_pending", Job: job, Result: json.RawMessage(`{"status":"success"}`)}, released: make(chan struct{})}
	runner := forbiddenRunner{started: make(chan struct{})}
	scheduler := dispatcher.New(config.Config{Runtime: config.Runtime{Interval: 1, MaxWorkers: 1, MaxProjects: 1, MaxProjectWorkers: 1}}, runner)
	scheduler.Client = server
	if err := scheduler.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	select {
	case <-server.released:
		if !server.applied {
			t.Fatal("lease released before saved result settlement")
		}
	case <-runner.started:
		t.Fatal("saved result replayed model/tool work")
	case <-time.After(3 * time.Second):
		t.Fatal("saved result recovery did not finish")
	}
}
