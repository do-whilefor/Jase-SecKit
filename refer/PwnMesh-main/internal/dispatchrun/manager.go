// Package dispatchrun owns execution and container lifecycles independently of
// scheduling policy. Its coordinator methods run on one loop; worker goroutines
// publish completion values without accessing policy state.
package dispatchrun

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/protocol"
)

type Runner interface {
	Run(context.Context, config.Worker, protocol.Job) (protocol.Result, error)
	Cleanup(context.Context, string, string) error
	Projects(context.Context) ([]string, error)
}

type Options struct {
	Server                  controlclient.Server
	Runner                  Runner
	Namespace               string
	Interval                int
	LeaseTimeout            time.Duration
	MaxWorkers, MaxProjects int
	HealthMode              string
	CheckHealth             func(context.Context, config.Worker, config.Task) error
	Wake                    func()
}

// Assignment is transferred to the manager when launched or resumed. Its Job
// and Worker environment remain immutable for that execution.
type Assignment struct {
	Job         protocol.Job
	Worker      config.Worker
	Lease       controlclient.Lease
	Execution   board.Execution
	UrgentInput bool
}

type task struct {
	Assignment
	Cancel          context.CancelFunc
	Root            context.Context
	LeaseTimeout    time.Duration
	committedAt     atomic.Int64
	staleInputAt    time.Time
	observedMetrics *protocol.DecisionMetrics
}

type finished struct {
	Task    *task
	Outcome string
	Err     error
}

type cleaned struct {
	ID, State string
	Err       error
}

// Active exposes only immutable identity, never a live task or its mutable result.
type Active struct {
	RunID, ProjectID, Kind, Backend, Intent string
	Generation                              int64
}

// Completion transfers final values only after the execution goroutine finishes.
type Completion struct {
	Assignment
	Outcome      string
	Err          error
	StaleInputAt time.Time
}

type Manager struct {
	client         controlclient.Server
	runner         Runner
	namespace      string
	interval       int
	leaseTimeout   time.Duration
	healthMode     string
	checkHealth    func(context.Context, config.Worker, config.Task) error
	notify         func()
	running        map[string]*task
	cleanup        map[string]string
	cleaned        map[string]string
	restartCleaned map[string]int64
	cleanupCursor  int
	done           chan finished
	cleanupDone    chan cleaned
	wg             sync.WaitGroup
}

func New(o Options) *Manager {
	return &Manager{client: o.Server, runner: o.Runner, namespace: o.Namespace,
		interval: o.Interval, leaseTimeout: o.LeaseTimeout, healthMode: o.HealthMode,
		checkHealth: o.CheckHealth, notify: o.Wake, running: map[string]*task{},
		cleanup: map[string]string{}, cleaned: map[string]string{}, restartCleaned: map[string]int64{},
		done: make(chan finished, o.MaxWorkers), cleanupDone: make(chan cleaned, o.MaxProjects+maxConcurrentCleanups)}
}

func (m *Manager) wake() {
	if m.notify != nil {
		m.notify()
	}
}

func (m *Manager) Count() int              { return len(m.running) }
func (m *Manager) Has(id string) bool      { return m.running[id] != nil }
func (m *Manager) Cleaning(id string) bool { return m.cleanup[id] != "" }
func (m *Manager) Running() []Active {
	active := make([]Active, 0, len(m.running))
	for id, t := range m.running {
		active = append(active, Active{RunID: id, ProjectID: t.Job.Graph.Project.ID,
			Generation: t.Job.Graph.Project.Generation, Kind: t.Job.Kind,
			Backend: t.Worker.Name, Intent: t.Lease.Intent})
	}
	return active
}

func (m *Manager) Drain() []Completion {
	var completed []Completion
	for {
		select {
		case f := <-m.done:
			delete(m.running, f.Task.Job.RunID)
			completed = append(completed, Completion{Assignment: f.Task.Assignment,
				Outcome: f.Outcome, Err: f.Err, StaleInputAt: f.Task.staleInputAt})
		default:
			m.drainCleanup()
			return completed
		}
	}
}

func (m *Manager) StopPrevious(ctx context.Context) error {
	old, err := m.runner.Projects(ctx)
	if err != nil {
		return err
	}
	for _, id := range old {
		if err := m.runner.Cleanup(ctx, id, "stopped"); err != nil {
			return err
		}
	}
	return nil
}

func (m *Manager) Stop() {
	for _, t := range m.running {
		t.Cancel()
	}
	m.wg.Wait()
}

func (m *Manager) Reconcile(ctx context.Context, summaries []board.Summary) {
	projects := make(map[string]board.Project, len(summaries))
	for _, summary := range summaries {
		projects[summary.ID] = summary.Project
		if summary.Status == "active" {
			delete(m.cleaned, summary.ID)
		}
	}
	for _, t := range m.running {
		project := projects[t.Job.Graph.Project.ID]
		if t.Job.Graph.Project.Generation != project.Generation {
			t.Cancel()
			continue
		}
		if project.Status != "active" {
			if project.Status == "completed" && m.decisionFinishAllowed(ctx, t) {
				continue
			}
			t.Cancel()
		}
	}
}

func (m *Manager) CancelStale(project board.Project) bool {
	stale := false
	for _, t := range m.running {
		if t.Job.Graph.Project.ID == project.ID && t.Job.Graph.Project.Generation != project.Generation {
			t.Cancel()
			stale = true
		}
	}
	return stale
}

func (m *Manager) Launch(ctx context.Context, job protocol.Job, worker config.Worker, trigger string, urgent bool) error {
	var id [16]byte
	if _, err := rand.Read(id[:]); err != nil {
		return err
	}
	job.RunID = hex.EncodeToString(id[:])
	lease := controlclient.Lease{Run: worker.Name + "@" + job.RunID, Kind: job.Kind}
	if job.Kind != "reason" && job.Kind != "curate" {
		lease.Intent = job.Intent.ID
	}
	if err := m.client.Claim(ctx, job.Graph.Project.ID, lease, trigger); err != nil {
		return err
	}
	t := &task{Assignment: Assignment{Job: job, Worker: worker, Lease: lease, UrgentInput: urgent}}
	if err := m.register(ctx, t); err != nil {
		_ = m.client.Release(ctx, job.Graph.Project.ID, lease)
		return err
	}
	m.start(ctx, t)
	return nil
}

func (m *Manager) Load(ctx context.Context, summary board.ExecutionSummary) (Assignment, error) {
	a := Assignment{Lease: controlclient.Lease{Run: summary.Lease, Kind: summary.Kind, Intent: summary.Intent}}
	var err error
	a.Execution, err = m.client.Execution(ctx, summary.ProjectID, summary.ID, m.namespace)
	if err != nil || !a.Execution.Pending() {
		return a, err
	}
	if err := json.Unmarshal(a.Execution.Job, &a.Job); err != nil {
		return a, fmt.Errorf("execution %s has invalid job: %w", summary.ID, err)
	}
	return a, nil
}

func (m *Manager) Resume(ctx context.Context, a Assignment) error {
	var err error
	a.Execution, err = m.client.Resume(ctx, a.Job.Graph.Project.ID, a.Job.RunID, a.Lease)
	if err != nil {
		return err
	}
	m.start(ctx, &task{Assignment: a})
	return nil
}

func (m *Manager) Terminal(a Assignment, status string, result protocol.Result) {
	m.terminal(&task{Assignment: a}, status, result)
}
