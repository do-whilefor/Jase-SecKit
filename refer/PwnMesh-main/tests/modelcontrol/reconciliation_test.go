package modelcontrol_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/dispatcher"
	"pwnmesh/internal/modelcontrol"
	"pwnmesh/internal/protocol"
)

type reconciliationServer struct{ controlclient.Server }

func (reconciliationServer) Installation(context.Context) (string, error) { return "test", nil }
func (reconciliationServer) DispatcherLease(context.Context, string, string, string, string) error {
	return nil
}
func (reconciliationServer) Settings(context.Context) (board.Settings, error) {
	return board.Settings{IntentTimeout: 30, ReasonTimeout: 30}, nil
}
func (reconciliationServer) List(context.Context) ([]board.Summary, error) { return nil, nil }
func (reconciliationServer) PendingExecutions(context.Context, string, int64) (board.ExecutionPage, error) {
	return board.ExecutionPage{}, nil
}

type cleanupRunner struct {
	started bool
	cleaned chan struct{}
	once    sync.Once
}

func (r *cleanupRunner) Projects(context.Context) ([]string, error) {
	if !r.started {
		r.started = true
		return nil, nil // Startup has no old containers to stop.
	}
	return []string{"deleted-project"}, nil
}
func (r *cleanupRunner) Cleanup(context.Context, string, string) error {
	r.once.Do(func() { close(r.cleaned) })
	return nil
}
func (*cleanupRunner) Run(context.Context, config.Worker, protocol.Job) (protocol.Result, error) {
	panic("no active projects")
}

func TestSlowModelSettingsDoNotBlockProjectCleanup(t *testing.T) {
	blocked := make(chan struct{})
	unblock := make(chan struct{})
	var requests atomic.Int32
	api := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != modelcontrol.SettingsPath {
			t.Error("unexpected model control endpoint")
			http.NotFound(w, r)
			return
		}
		n := requests.Add(1)
		if n == 1 {
			_, _ = w.Write([]byte(`{"found":false}`))
			return
		}
		if n == 2 {
			close(blocked)
		}
		select {
		case <-r.Context().Done():
		case <-unblock:
		}
	}))
	defer api.Close()
	defer close(unblock)
	runner := &cleanupRunner{cleaned: make(chan struct{})}
	s := dispatcher.New(config.Config{Server: api.URL, ModelSettingsSource: "server", ControlToken: strings.Repeat("s", 64), Runtime: config.Runtime{Interval: 1, MaxWorkers: 1, MaxProjects: 1}}, runner)
	s.Client = reconciliationServer{}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- s.Run(ctx) }()
	defer func() {
		cancel()
		select {
		case err := <-done:
			if err != nil {
				t.Error(err)
			}
		case <-time.After(3 * time.Second):
			t.Error("dispatcher did not stop")
		}
	}()
	select {
	case <-blocked:
	case <-time.After(3 * time.Second):
		t.Fatal("runtime settings were not requested")
	}
	select {
	case <-runner.cleaned:
	case <-time.After(2 * time.Second):
		t.Fatal("stalled model settings blocked deleted-project cleanup")
	}
}

type recoveryGateServer struct {
	reconciliationServer
	status   string
	job      json.RawMessage
	reads    int
	applied  bool
	released chan struct{}
}

func (*recoveryGateServer) List(context.Context) ([]board.Summary, error) {
	return []board.Summary{{Project: board.Project{ID: "project", Status: "active", OrchestrationVersion: 1}}}, nil
}
func (s *recoveryGateServer) PendingExecutions(context.Context, string, int64) (board.ExecutionPage, error) {
	return board.ExecutionPage{Items: []board.ExecutionSummary{{ProjectID: "project", ID: "run", Backend: "go", Kind: "explore", Intent: "step", Lease: "go@run", Status: s.status}}}, nil
}
func (s *recoveryGateServer) Execution(context.Context, string, string, string) (board.Execution, error) {
	s.reads++
	return board.Execution{ProjectID: "project", ID: "run", Backend: "go", Kind: "explore", Intent: "step", Lease: "go@run", Status: s.status, Job: s.job, Result: json.RawMessage(`{"status":"success"}`)}, nil
}
func (s *recoveryGateServer) Resume(ctx context.Context, project, run string, _ controlclient.Lease) (board.Execution, error) {
	return s.Execution(ctx, project, run, "")
}
func (s *recoveryGateServer) Apply(context.Context, string, string, controlclient.Lease) (string, error) {
	s.applied = true
	return "succeeded", nil
}
func (s *recoveryGateServer) Release(context.Context, string, controlclient.Lease) error {
	close(s.released)
	return nil
}

func TestUnavailableSettingsBlockModelRecoveryButAllowSavedResults(t *testing.T) {
	job, err := json.Marshal(protocol.Job{RunID: "run", Kind: "explore", GraphRPC: true, ResultContractVersion: 2, Graph: board.Graph{Project: board.Project{ID: "project", Status: "active", OrchestrationVersion: 1}}, Intent: &board.Intent{ID: "step"}})
	if err != nil {
		t.Fatal(err)
	}
	for _, status := range []string{"running", "result_pending"} {
		t.Run(status, func(t *testing.T) {
			server := &recoveryGateServer{status: status, job: job, released: make(chan struct{})}
			s := dispatcher.New(config.Config{ModelSettingsSource: "server", Runtime: config.Runtime{Interval: 1, MaxWorkers: 1, MaxProjects: 1, MaxProjectWorkers: 1}}, &cleanupRunner{})
			s.Client = server
			// No acquired owner means the current settings lookup must fail.
			if err := s.Step(context.Background()); err == nil || !strings.Contains(err.Error(), "active dispatcher ownership") {
				t.Fatalf("settings lookup did not fail: %v", err)
			}
			if status == "running" {
				if server.reads != 0 {
					t.Fatal("unfinished work passed the current settings failure gate")
				}
				return
			}
			select {
			case <-server.released:
				if !server.applied {
					t.Fatal("saved result released without settlement")
				}
			case <-time.After(time.Second):
				t.Fatal("saved result did not settle while model settings were unavailable")
			}
		})
	}
}
