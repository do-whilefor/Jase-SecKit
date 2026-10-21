package dispatcher

import (
	"context"
	"errors"
	"log/slog"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/dispatchrun"
)

func (s *Scheduler) loadLeaseTimeout(ctx context.Context) error {
	if s.Config.Runtime.Interval <= 0 || int64(s.Config.Runtime.Interval) > board.MaxDurationSeconds/2 {
		return errors.New("heartbeat interval must be positive seconds within the supported duration")
	}
	settings, err := s.Client.Settings(ctx)
	if err != nil {
		return err
	}
	if settings.IntentTimeout < 5 || settings.ReasonTimeout < 5 {
		return errors.New("server lease timeouts must be at least 5 seconds")
	}
	if int64(settings.IntentTimeout) > board.MaxDurationSeconds || int64(settings.ReasonTimeout) > board.MaxDurationSeconds {
		return errors.New("server lease timeouts exceed the supported duration")
	}
	timeout := time.Duration(min(settings.IntentTimeout, settings.ReasonTimeout)) * time.Second
	if timeout <= time.Duration(s.Config.Runtime.Interval)*time.Second {
		return errors.New("heartbeat interval must be shorter than each server lease timeout")
	}
	s.leaseTimeout = timeout
	return nil
}

func (s *Scheduler) prepareRun(ctx context.Context) error {
	if err := s.loadLeaseTimeout(ctx); err != nil {
		return err
	}
	if s.leaseTimeout < 2*time.Duration(s.Config.Runtime.Interval)*time.Second {
		slog.Warn("server lease timeout leaves little heartbeat slack", "interval", s.Config.Runtime.Interval, "lease_timeout", int(s.leaseTimeout/time.Second))
	}
	// With one dispatcher, old managed executions cannot survive a restart and
	// keep exploring while model readiness is checked or leases are reassigned.
	// Keep workspace contents.
	s.ensureRuns()
	if err := s.runs.StopPrevious(ctx); err != nil {
		return err
	}
	_ = s.Health(ctx, false)
	return nil
}

func (s *Scheduler) prepareStep(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := s.bindOwnership(ctx); err != nil {
		return err
	}
	if s.leaseTimeout == 0 {
		if err := s.loadLeaseTimeout(ctx); err != nil {
			return err
		}
	}
	s.ensureRuns()
	s.reap()
	return nil
}

func (s *Scheduler) runLoop(parent, ctx context.Context) error {
	tick := time.NewTicker(time.Duration(s.Config.Runtime.Interval) * time.Second)
	defer tick.Stop()
	deadline := time.NewTimer(time.Hour)
	deadline.Stop()
	defer deadline.Stop()
	for {
		if err := s.Step(ctx); err != nil && ctx.Err() == nil {
			slog.Warn("dispatcher tick failed", "error", err)
		}
		var ready <-chan time.Time
		if !s.nextWake.IsZero() {
			deadline.Reset(time.Until(s.nextWake))
			ready = deadline.C
		}
		select {
		case <-ctx.Done():
			if parent.Err() == nil {
				return context.Cause(ctx)
			}
			return nil
		case <-tick.C:
		case <-s.wakeup:
		case <-ready:
		}
		deadline.Stop()
	}
}

// Completion records stay in their existing queues until Step reaps them.
// Coalesce notifications without blocking workers or losing queued outcomes.
func (s *Scheduler) wake() {
	select {
	case s.wakeup <- struct{}{}:
	default:
	}
}

// Capture execution dependencies after ownership is acquired and before work starts.
// Tests and embeddings may replace Client before the first Run or Step.
func (s *Scheduler) ensureRuns() {
	if s.runs != nil {
		return
	}
	s.runs = dispatchrun.New(dispatchrun.Options{
		Server: s.Client, Runner: s.Runner, Namespace: s.namespace(),
		Interval: s.Config.Runtime.Interval, LeaseTimeout: s.leaseTimeout,
		MaxWorkers: s.Config.Runtime.MaxWorkers, MaxProjects: s.Config.Runtime.MaxProjects,
		HealthMode: s.Config.Runtime.HealthMode, CheckHealth: s.taskHealth(), Wake: s.wake,
	})
}
