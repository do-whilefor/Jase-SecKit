package dispatchrun

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/protocol"
)

func (m *Manager) runTask(ctx context.Context, t *task) (outcome string, runErr error) {
	started := time.Now()
	defer func() {
		if attrs := controlOutcomeAttrs(t, outcome, runErr, started, time.Now()); attrs != nil {
			slog.LogAttrs(context.Background(), slog.LevelInfo, "control task finished", attrs...)
		}
	}()
	ctx, cancel := context.WithCancelCause(ctx)
	defer cancel(nil)
	leaseCtx, stopLease := context.WithCancel(ctx)
	heartbeatDone := make(chan struct{})
	go func() { defer close(heartbeatDone); m.heartbeat(leaseCtx, t, cancel) }()
	defer func() {
		stopLease()
		<-heartbeatDone
		if cause := context.Cause(ctx); outcome != "success" && dependencyInvalidated(cause) && (t.Root == nil || t.Root.Err() == nil) {
			// The same terminal boundary covers cancellation during model calls,
			// health checks and infrastructure retry backoff. Recovery must not
			// restart work after its accepted upstream result became invalid.
			m.terminal(t, "cancelled", protocol.Result{Status: "failed", FailureKind: "dependency_invalidated", Error: cause.Error()})
			outcome, runErr = "cancelled", cause
		}
		// Invalidation can interrupt startup, a model call, or recovery backoff.
		// Reconcile once after the heartbeat stops, before releasing this lease.
		if cause := context.Cause(ctx); outcome != "failed" && outcome != "success" && decisionStateChanged(cause) && (t.Root == nil || t.Root.Err() == nil) {
			committed, err := m.controlCommitted(ctx, t)
			switch {
			case err != nil:
				outcome, runErr = "interrupted", err
			case committed:
				outcome, runErr = "success", nil
			default:
				m.terminal(t, "failed", protocol.Result{Status: "failed", FailureKind: "state_changed", Error: cause.Error()})
				outcome, runErr = "failed", cause
			}
		}
		releaseCtx, c := context.WithTimeout(context.Background(), 5*time.Second)
		defer c()
		if outcome == "interrupted" && t.observedMetrics != nil && t.Execution.Status != "result_pending" {
			// A graceful shutdown can end before a final Worker result. Retain
			// the latest cumulative observation without settling business output.
			if err := m.status(releaseCtx, t, "running", protocol.Result{Metrics: t.observedMetrics}); err != nil {
				slog.Warn("interrupted execution observation could not be saved", "run", t.Job.RunID, "error", err)
			}
		}
		_ = m.client.Release(releaseCtx, t.Job.Graph.Project.ID, t.Lease)
	}()
	return m.runRegistered(ctx, t, func() { stopLease(); <-heartbeatDone })
}
func (m *Manager) renewLease(ctx context.Context, t *task) error {
	return m.renewLeaseWithVersion(ctx, t, t.Job.Kind != "reason" || t.Job.Decision == nil || t.Job.Decision.Version != 2)
}

// A running batch planner can refresh its stable read view after a conflict.
// Its initial whole-graph hash must not kill that session when producers publish
// new facts. Startup/recovery still reject obsolete inputs before model work;
// periodic renewal retains the project, generation and execution lease fences.
func (m *Manager) renewLeaseWithVersion(ctx context.Context, t *task, checkInput bool) error {
	version := ""
	if checkInput {
		version = immutableInputVersion(t)
	}
	return m.client.Renew(ctx, t.Job.Graph.Project.ID, t.Lease, version)
}

func (m *Manager) heartbeat(ctx context.Context, t *task, cancel context.CancelCauseFunc) {
	interval := time.Duration(m.interval) * time.Second
	timeout := t.LeaseTimeout
	if timeout <= interval {
		timeout = 2 * interval
	}
	// A valid configured interval may consume most of the lease. Renew early
	// enough to leave another interval for the request and one for shutdown;
	// otherwise the first renewal can start with an already expired deadline.
	interval = min(interval, timeout/3)
	tick := time.NewTicker(interval)
	defer tick.Stop()
	last := time.Now()
	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			// Queueing behind other transactions must not turn a healthy busy
			// Server into a hard cancellation after only two heartbeat intervals.
			// Stop before the actual Server lease expires, including queue time.
			callCtx, c := context.WithDeadline(ctx, last.Add(timeout-interval))
			err := m.renewLease(callCtx, t)
			c()
			if ctx.Err() != nil {
				return
			}
			if err == nil {
				last = time.Now()
				continue
			}
			var pe *controlclient.ProtocolError
			if errors.As(err, &pe) && (pe.Status == 403 || pe.Status == 404 || pe.Status == 409) || time.Since(last) >= timeout-interval {
				if m.decisionFinishAllowed(ctx, t) {
					// A commit revokes its lease before the Worker receives the
					// acknowledgement. Give that reply and metrics a bounded drain.
					timer := time.NewTimer(time.Until(time.Unix(0, t.committedAt.Load()).Add(decisionFinishGrace)))
					select {
					case <-ctx.Done():
						timer.Stop()
					case <-timer.C:
						cancel(err)
					}
					return
				}
				if decisionStateChanged(err) {
					slog.Info("decision input changed; cancelling stale run", "project", t.Job.Graph.Project.ID, "run", t.Job.RunID)
				}
				cancel(err)
				return
			}
		}
	}
}
