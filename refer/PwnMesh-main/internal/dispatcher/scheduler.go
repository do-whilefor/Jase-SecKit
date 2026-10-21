package dispatcher

import (
	"context"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/dispatchrun"
	"pwnmesh/internal/modelconfig"
	"pwnmesh/internal/modelcontrol"
)

type Runner = dispatchrun.Runner

type checkpoint struct{ Facts, Hints, Open int }
type reasonWait struct {
	First, Changed time.Time
	Revision       int64
	Urgent         bool
}

const reasonQuietPeriod = 15 * time.Second
const reasonMaxWait = time.Minute

type Scheduler struct {
	runs              *dispatchrun.Manager
	runtimeModels     *modelcontrol.Client
	modelSettings     modelconfig.Settings
	modelLoaded       bool
	modelSettingsErr  error
	Config            config.Config
	Client            controlclient.Server
	Runner            Runner
	admitted          map[string]bool
	checkpoints       map[string]checkpoint
	reasonWaits       map[string]reasonWait
	curationWaits     map[string]reasonWait
	controlConflicts  map[string]time.Time
	unhealthy         map[string]time.Time
	incompatible      map[string]string
	rejected          map[string]time.Time
	deliveryWaits     map[string]time.Time
	wakeup            chan struct{}
	nextWake          time.Time
	cursor            int
	pendingExecutions []board.ExecutionSummary
	decisionRevisions map[string]int64
	schedules         map[string]board.SchedulePage
	generations       map[string]int64
	leaseTimeout      time.Duration
	// CheckHealth overrides the model readiness probe in tests or embeddings.
	CheckHealth func(context.Context, config.Worker) error
}

func New(c config.Config, r Runner) *Scheduler {
	s := &Scheduler{Config: c, Runner: r, Client: &Client{Base: c.Server},
		admitted: map[string]bool{}, checkpoints: map[string]checkpoint{},
		unhealthy: map[string]time.Time{}, rejected: map[string]time.Time{},
		decisionRevisions: map[string]int64{}, schedules: map[string]board.SchedulePage{},
		generations: map[string]int64{}, reasonWaits: map[string]reasonWait{},
		controlConflicts: map[string]time.Time{}, deliveryWaits: map[string]time.Time{},
		wakeup: make(chan struct{}, 1)}
	s.configureGraphHandler()
	s.configureInputReader()
	return s
}

// Run holds dispatcher ownership through startup, scheduling and worker shutdown.
func (s *Scheduler) Run(ctx context.Context) error {
	parent := ctx
	ctx, release, err := s.acquireDispatcher(ctx)
	if err != nil {
		return err
	}
	defer release()
	if err := s.prepareRun(ctx); err != nil {
		return err
	}
	defer s.runs.Stop()
	return s.runLoop(parent, ctx)
}

// Step reconciles existing work before admitting new executions. Configuration
// errors must not prevent cancellation, recovery settlement or container cleanup.
func (s *Scheduler) Step(ctx context.Context) error {
	s.nextWake = time.Time{}
	if err := s.prepareStep(ctx); err != nil {
		return err
	}
	states, active, err := s.reconcileProjects(ctx)
	if err != nil {
		return err
	}
	// Remote settings must not delay cancellation or monopolize reconciliation.
	// Refresh before recovery so unfinished work uses the current model gate.
	settingsCtx, cancel := context.WithTimeout(ctx, time.Duration(max(1, min(s.Config.Runtime.Interval, 3)))*time.Second)
	s.modelSettingsErr = s.refreshModelSettings(settingsCtx)
	cancel()
	if err := s.loadExecutions(ctx); err != nil {
		return err
	}
	s.releaseIdleAdmissions()
	if err := s.recoverExecutions(ctx, states); err != nil {
		return err
	}
	if err := s.runs.CleanupInactive(ctx, states); err != nil {
		return err
	}
	if s.modelSettingsErr != nil {
		return s.modelSettingsErr
	}
	return s.admit(ctx, active)
}
