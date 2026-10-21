package dispatcher_test

import (
	"context"
	"errors"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/dispatcher"
	"pwnmesh/internal/dispatchrun"
	"pwnmesh/internal/protocol"
)

type lifecycleServer struct {
	controlclient.Server
	stopped       atomic.Bool
	mu            sync.Mutex
	events        []string
	terminal      protocol.Result
	ownerReleased chan struct{}
	taskReleased  chan struct{}
}

func (s *lifecycleServer) record(event string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, event)
}
func (*lifecycleServer) Installation(context.Context) (string, error) { return "installation", nil }
func (s *lifecycleServer) DispatcherLease(_ context.Context, _, _, _, op string) error {
	if op == "release" {
		s.record("owner released")
		close(s.ownerReleased)
	}
	return nil
}
func (*lifecycleServer) Settings(context.Context) (board.Settings, error) {
	return board.Settings{IntentTimeout: 30, ReasonTimeout: 30}, nil
}
func (s *lifecycleServer) List(context.Context) ([]board.Summary, error) {
	status := "active"
	if s.stopped.Load() {
		status = "stopped"
	}
	return []board.Summary{{Project: board.Project{ID: "project", Status: status, OrchestrationVersion: 1}}}, nil
}
func (*lifecycleServer) PendingExecutions(context.Context, string, int64) (board.ExecutionPage, error) {
	return board.ExecutionPage{}, nil
}
func (*lifecycleServer) Schedule(context.Context, string, controlclient.ScheduleQuery) (board.SchedulePage, error) {
	return board.SchedulePage{Project: board.Project{ID: "project", Status: "active", OrchestrationVersion: 1}, Initial: true, ExecutionChecks: map[string]board.ExecutionCheck{"reason:": {}}}, nil
}
func (*lifecycleServer) Claim(context.Context, string, controlclient.Lease, string) error { return nil }
func (*lifecycleServer) Prepare(_ context.Context, execution board.Execution, _ controlclient.Lease) (board.Execution, error) {
	execution.Status = "prepared"
	return execution, nil
}
func (s *lifecycleServer) ChangeStatus(_ context.Context, _, _, status string, result protocol.Result, _ controlclient.Lease) error {
	if status != "running" {
		s.mu.Lock()
		s.events = append(s.events, status)
		s.terminal = result
		s.mu.Unlock()
	}
	return nil
}
func (*lifecycleServer) Renew(context.Context, string, controlclient.Lease, string) error { return nil }
func (s *lifecycleServer) Release(context.Context, string, controlclient.Lease) error {
	s.record("task released")
	close(s.taskReleased)
	return nil
}

type lifecycleRunner struct {
	server   *lifecycleServer
	started  chan struct{}
	canceled chan error
	finish   chan struct{}
	cleaned  chan struct{}
	live     atomic.Bool
	once     sync.Once
}

func (*lifecycleRunner) BindOwner(string) error { return nil }
func (r *lifecycleRunner) Projects(context.Context) ([]string, error) {
	if !r.live.Load() {
		return nil, nil
	}
	return []string{"project"}, nil
}
func (r *lifecycleRunner) Cleanup(_ context.Context, project, state string) error {
	if project != "project" || state != "stopped" {
		return errors.New("unexpected cleanup target or state")
	}
	r.once.Do(func() { close(r.cleaned) })
	return nil
}
func (r *lifecycleRunner) Run(ctx context.Context, _ config.Worker, job protocol.Job) (protocol.Result, error) {
	if job.WorkerType != "pi" {
		return protocol.Result{}, errors.New("dispatcher did not assign the Pi runtime")
	}
	r.live.Store(true)
	close(r.started)
	<-ctx.Done()
	r.canceled <- context.Cause(ctx)
	<-r.finish
	r.server.record("worker exited")
	return protocol.Result{}, ctx.Err()
}

func TestLifecycleDistinguishesProjectStopFromDispatcherShutdown(t *testing.T) {
	for _, stopProject := range []bool{false, true} {
		name := "dispatcher shutdown"
		if stopProject {
			name = "project stop"
		}
		t.Run(name, func(t *testing.T) {
			server := &lifecycleServer{ownerReleased: make(chan struct{}), taskReleased: make(chan struct{})}
			runner := &lifecycleRunner{server: server, started: make(chan struct{}), canceled: make(chan error, 1), finish: make(chan struct{}), cleaned: make(chan struct{})}
			scheduler := dispatcher.New(config.Config{Runtime: config.Runtime{Interval: 1, MaxWorkers: 1, MaxProjects: 1, MaxProjectWorkers: 1, HealthMode: "disabled"}, Workers: []config.Worker{{Name: "pi", MaxRunning: 1, TaskTypes: []string{"reason"}}}}, runner)
			scheduler.Client = server
			ctx, cancel := context.WithCancel(context.Background())
			done := make(chan error, 1)
			go func() { done <- scheduler.Run(ctx) }()
			var finish sync.Once
			allowExit := func() { finish.Do(func() { close(runner.finish) }) }
			t.Cleanup(func() {
				cancel()
				allowExit()
				select {
				case <-server.ownerReleased:
				case <-time.After(3 * time.Second):
					t.Error("dispatcher did not release ownership")
				}
			})
			select {
			case <-runner.started:
			case <-time.After(3 * time.Second):
				t.Fatal("worker did not start")
			}
			if stopProject {
				server.stopped.Store(true)
			} else {
				cancel()
			}
			select {
			case cause := <-runner.canceled:
				want := protocol.ErrInterrupted
				if stopProject {
					want = context.Canceled
				}
				if !errors.Is(cause, want) {
					t.Fatalf("cancellation cause = %v, want %v", cause, want)
				}
			case <-time.After(3 * time.Second):
				t.Fatal("worker was not canceled")
			}
			select {
			case <-server.ownerReleased:
				t.Fatal("ownership released while worker was still running")
			case <-time.After(30 * time.Millisecond):
			}
			allowExit()
			if stopProject {
				select {
				case <-server.taskReleased:
				case <-time.After(3 * time.Second):
					t.Fatal("stopped task did not release its lease")
				}
				select {
				case <-runner.cleaned:
				case <-time.After(3 * time.Second):
					t.Fatal("stopped project container was not cleaned")
				}
				cancel()
			}
			select {
			case err := <-done:
				if err != nil {
					t.Fatal(err)
				}
			case <-time.After(3 * time.Second):
				t.Fatal("dispatcher did not stop")
			}
			want := []string{"worker exited", "task released", "owner released"}
			if stopProject {
				want = []string{"worker exited", "cancelled", "task released", "owner released"}
				if server.terminal.FailureKind != "hard_cancelled" {
					t.Fatalf("project cancellation result = %+v", server.terminal)
				}
			}
			if !reflect.DeepEqual(server.events, want) {
				t.Fatalf("events = %v, want %v", server.events, want)
			}
		})
	}
}

type cleanupAttempt struct {
	project, state string
	result         chan error
}

type restartRunner struct {
	*lifecycleRunner
	attempts chan cleanupAttempt
}

func (r *restartRunner) Cleanup(ctx context.Context, project, state string) error {
	attempt := cleanupAttempt{project: project, state: state, result: make(chan error, 1)}
	r.attempts <- attempt
	select {
	case err := <-attempt.result:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}

func TestRestartWaitsForOldExecutionAndSuccessfulCleanup(t *testing.T) {
	server := &lifecycleServer{ownerReleased: make(chan struct{}), taskReleased: make(chan struct{})}
	runner := &restartRunner{lifecycleRunner: &lifecycleRunner{server: server, started: make(chan struct{}), canceled: make(chan error, 1), finish: make(chan struct{})}, attempts: make(chan cleanupAttempt, 2)}
	wake := make(chan struct{}, 1)
	manager := dispatchrun.New(dispatchrun.Options{Server: server, Runner: runner, Interval: 1, LeaseTimeout: 30 * time.Second, MaxWorkers: 1, MaxProjects: 1, Wake: func() {
		select {
		case wake <- struct{}{}:
		default:
		}
	}})
	ctx, cancel := context.WithCancel(context.Background())
	var finish sync.Once
	allowExit := func() { finish.Do(func() { close(runner.finish) }) }
	t.Cleanup(func() { cancel(); allowExit(); manager.Stop() })
	project := board.Project{ID: "project", Status: "active", Generation: 1, OrchestrationVersion: 1}
	if err := manager.Launch(ctx, protocol.Job{Kind: "reason", WorkerType: "pi", Graph: board.Graph{Project: project}}, config.Worker{Name: "pi"}, "initial", false); err != nil {
		t.Fatal(err)
	}
	select {
	case <-runner.started:
	case <-time.After(time.Second):
		t.Fatal("old execution did not start")
	}
	project.Generation++
	if !manager.CancelStale(project) || manager.RestartReady(ctx, project) || manager.Cleaning(project.ID) {
		t.Fatal("restart cleanup overtook the old execution")
	}
	allowExit()
	select {
	case <-wake:
	case <-time.After(time.Second):
		t.Fatal("old execution did not finish")
	}
	if completed := manager.Drain(); len(completed) != 1 || completed[0].Outcome != "cancelled" || manager.Count() != 0 {
		t.Fatalf("old execution completion = %+v", completed)
	}
	for attempt, failure := range []error{errors.New("temporary cleanup failure"), nil} {
		if manager.RestartReady(ctx, project) || !manager.Cleaning(project.ID) {
			t.Fatal("new generation was admitted before cleanup")
		}
		var cleanup cleanupAttempt
		select {
		case cleanup = <-runner.attempts:
		case <-time.After(time.Second):
			t.Fatal("restart cleanup did not start")
		}
		if cleanup.project != "project" || cleanup.state != "restart:2" || manager.RestartReady(ctx, project) {
			t.Fatalf("incorrect or unfinished restart cleanup: %+v", cleanup)
		}
		cleanup.result <- failure
		deadline := time.Now().Add(time.Second)
		for manager.Cleaning(project.ID) && time.Now().Before(deadline) {
			manager.Drain()
			time.Sleep(time.Millisecond)
		}
		if manager.Cleaning(project.ID) {
			t.Fatal("cleanup completion was not drained")
		}
		if attempt == 1 && !manager.RestartReady(ctx, project) {
			t.Fatal("successful cleanup did not release the restart fence")
		}
	}
	select {
	case duplicate := <-runner.attempts:
		t.Fatalf("duplicate restart cleanup: %+v", duplicate)
	default:
	}
}
