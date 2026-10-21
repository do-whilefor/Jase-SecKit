package dispatchrun

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/protocol"
)

func (m *Manager) register(ctx context.Context, t *task) error {
	// New runs have one server-owned immutable snapshot. Templates never carry
	// graph data; recovery continues to use the exact registered Job below.
	t.Job.Graph = board.Graph{Project: t.Job.Graph.Project}
	t.Job.State = nil
	raw, err := json.Marshal(t.Job)
	if err != nil {
		return err
	}
	e := board.Execution{ProjectID: t.Job.Graph.Project.ID, ID: t.Job.RunID, Namespace: m.namespace, Backend: t.Worker.Name, Kind: t.Job.Kind, Intent: t.Lease.Intent, Lease: t.Lease.Run, Job: raw}
	if t.Execution, err = m.client.Prepare(ctx, e, t.Lease); err != nil {
		return err
	}
	// The HTTP decoder canonicalizes embedded JSON objects. Run exactly the
	// stored job so RawMessage ordering cannot change the identity on recovery.
	if err = json.Unmarshal(t.Execution.Job, &t.Job); err != nil {
		return err
	}
	return nil
}

func (m *Manager) start(ctx context.Context, t *task) {
	// Dispatcher shutdown is a recoverable interruption. A project stop or
	// lease loss is a hard cancellation. Detach parent cancellation only long
	// enough to relay this distinction to the Docker process controller.
	runCtx, cancelCause := context.WithCancelCause(context.WithoutCancel(ctx))
	cancel := func() {
		if ctx.Err() != nil {
			cancelCause(protocol.ErrInterrupted)
		} else {
			cancelCause(context.Canceled)
		}
	}
	t.Cancel = cancel
	t.Root = ctx
	t.LeaseTimeout = m.leaseTimeout
	go func() {
		select {
		case <-ctx.Done():
			cancelCause(protocol.ErrInterrupted)
		case <-runCtx.Done():
		}
	}()
	m.running[t.Job.RunID] = t
	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		defer cancel()
		outcome, err := m.runTask(runCtx, t)
		m.done <- finished{t, outcome, err}
		m.wake()
	}()
}

func (m *Manager) status(ctx context.Context, t *task, status string, result protocol.Result) error {
	err := m.client.ChangeStatus(ctx, t.Job.Graph.Project.ID, t.Job.RunID, status, result, t.Lease)
	if err == nil && status == "result_pending" {
		t.Execution.Status = status
	}
	return err
}

func (m *Manager) terminal(t *task, status string, result protocol.Result) {
	if result.Metrics == nil {
		result.Metrics = t.observedMetrics
		if result.Metrics == nil && len(t.Execution.Result) != 0 {
			var saved protocol.Result
			if json.Unmarshal(t.Execution.Result, &saved) == nil {
				result.Metrics = saved.Metrics
			}
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := m.status(ctx, t, status, result); err == nil && status == "failed" && result.FailureKind == "state_changed" && immutableInputVersion(t) != "" {
		t.staleInputAt = time.Now()
	}
}

func (m *Manager) runRegistered(ctx context.Context, t *task, stopHeartbeat func()) (string, error) {
	if ok, err := m.controlCommitted(ctx, t); ok || err != nil {
		if ok {
			return "success", nil
		}
		return "interrupted", err
	}
	var result protocol.Result
	if len(t.Execution.Result) != 0 || t.Execution.Status == "result_pending" {
		var saved protocol.Result
		err := json.Unmarshal(t.Execution.Result, &saved)
		if err != nil && t.Execution.Status == "result_pending" {
			return "failed", err
		}
		if err == nil {
			t.observedMetrics = saved.Metrics
			if t.Execution.Status == "result_pending" {
				result = saved
			}
		}
	}
	if t.Execution.Status != "result_pending" {
		if m.healthMode == "startup_and_task" {
			if err := m.checkHealth(ctx, t.Worker, t.Job.Budget); err != nil {
				if ctx.Err() != nil {
					return "cancelled", ctx.Err()
				}
				return "unhealthy", err
			}
		}
		for attempt := 0; attempt <= 2; attempt++ {
			if err := m.status(ctx, t, "running", protocol.Result{Metrics: t.observedMetrics}); err != nil {
				var pe *controlclient.ProtocolError
				if errors.As(err, &pe) && (pe.Status == 403 || pe.Status == 404 || pe.Status == 409) {
					m.terminal(t, "cancelled", protocol.Result{Status: "failed", FailureKind: "invalidated_before_start", Error: err.Error()})
					return "cancelled", err
				}
				return "interrupted", err
			}
			var err error
			// Container startup and same-run recovery must not issue a request
			// against an input already superseded while the run was queued.
			if immutableInputVersion(t) != "" {
				err = m.renewLeaseWithVersion(ctx, t, true)
			}
			if err == nil {
				result, err = m.runner.Run(ctx, t.Worker, t.Job)
			}
			if result.Metrics != nil {
				result.Metrics = retainKnownChildUsage(t.observedMetrics, result.Metrics)
				t.observedMetrics = result.Metrics
				slog.Info("decision observation", "project", t.Job.Graph.Project.ID, "run", t.Job.RunID, "metrics", result.Metrics)
			}
			if committed, receiptErr := m.controlCommitted(ctx, t); committed || receiptErr != nil {
				if committed {
					m.observeDecision(ctx, t, result.Metrics)
					return "success", nil
				}
				return "interrupted", receiptErr
			}
			if ctx.Err() != nil {
				// Process-wide shutdown leaves a recoverable registry entry. Explicit
				// project/lease cancellation is terminal and cannot mint a fresh attempt.
				if t.Root != nil && t.Root.Err() != nil {
					return "interrupted", ctx.Err()
				}
				if decisionStateChanged(context.Cause(ctx)) {
					return "interrupted", context.Cause(ctx) // runTask persists after joining the heartbeat.
				}
				failure, detail := "hard_cancelled", ctx.Err().Error()
				if cause := context.Cause(ctx); dependencyInvalidated(cause) {
					failure, detail = "dependency_invalidated", cause.Error()
				}
				m.terminal(t, "cancelled", protocol.Result{Status: "failed", FailureKind: failure, Error: detail})
				return "cancelled", ctx.Err()
			}
			if err != nil {
				result = protocol.Result{Status: "failed", Retryable: true, FailureKind: "transient_infrastructure", Error: err.Error(), Metrics: t.observedMetrics}
				if decisionStateChanged(err) {
					result.FailureKind, result.Retryable = "state_changed", false
				}
			}
			if result.Status == "success" {
				break
			}
			if !result.Retryable || attempt == 2 {
				result.Retryable = false
				m.terminal(t, "failed", result)
				return "failed", errors.New(result.Error)
			}
			if err = m.status(ctx, t, "retryable", result); err != nil {
				return "interrupted", err
			}
			// The Worker persists its own recovery counter before issuing a request.
			// This short backoff never releases the step lease or resets its deadline.
			timer := time.NewTimer(time.Duration(attempt+1) * 100 * time.Millisecond)
			select {
			case <-ctx.Done():
				timer.Stop()
				return "interrupted", ctx.Err()
			case <-timer.C:
			}
		}
		if err := m.status(ctx, t, "result_pending", result); err != nil {
			return m.resultDeliveryFailure(ctx, t, result, err)
		}
	}
	// Stop lease renewal before settlement revokes the lease, so its final
	// heartbeat cannot cancel delivery of the accepted result.
	stopHeartbeat()
	status, err := m.client.Apply(ctx, t.Job.Graph.Project.ID, t.Job.RunID, t.Lease)
	if err != nil {
		return m.resultDeliveryFailure(ctx, t, result, err)
	}
	if status == "rejected" {
		return "rejected", nil
	}
	return "success", nil
}

// Partial observations cannot erase known child work. Retain a lower bound of
// each child counter, replacing its old contribution rather than adding totals.
// Complete final aggregation remains authoritative.
func retainKnownChildUsage(previous, current *protocol.DecisionMetrics) *protocol.DecisionMetrics {
	if previous == nil || current == nil || previous.UsageScope != "run_and_children" || previous.ChildUsage == nil ||
		(current.UsageScope != "run" && (current.UsageScope != "run_and_children" || current.ChildUsage == nil || !current.ChildUsage.Incomplete)) {
		return current
	}
	merged, old, children := *current, protocol.ChildUsage{}, *previous.ChildUsage
	if current.ChildUsage != nil {
		old = *current.ChildUsage
	}
	children.Sessions = max(children.Sessions, old.Sessions)
	children.ModelCalls = max(children.ModelCalls, old.ModelCalls)
	children.SummaryCalls = max(children.SummaryCalls, old.SummaryCalls)
	children.CompletedCalls = max(children.CompletedCalls, old.CompletedCalls)
	children.FailedCalls = max(children.FailedCalls, old.FailedCalls)
	children.UsageCalls = max(children.UsageCalls, old.UsageCalls)
	children.Usage.InputTokens = max(children.Usage.InputTokens, old.Usage.InputTokens)
	children.Usage.OutputTokens = max(children.Usage.OutputTokens, old.Usage.OutputTokens)
	children.Usage.CacheReadTokens = max(children.Usage.CacheReadTokens, old.Usage.CacheReadTokens)
	children.Usage.CacheWriteTokens = max(children.Usage.CacheWriteTokens, old.Usage.CacheWriteTokens)
	children.ModelDurationMS = max(children.ModelDurationMS, old.ModelDurationMS)
	children.ModelTiming.Calls = max(children.ModelTiming.Calls, old.ModelTiming.Calls)
	children.ModelTiming.ProviderCalls = max(children.ModelTiming.ProviderCalls, old.ModelTiming.ProviderCalls)
	children.ModelTiming.QueueMS = max(children.ModelTiming.QueueMS, old.ModelTiming.QueueMS)
	children.ModelTiming.ProviderMS = max(children.ModelTiming.ProviderMS, old.ModelTiming.ProviderMS)
	children.TotalInputBytes = max(children.TotalInputBytes, old.TotalInputBytes)
	if children.InputBytesBasis == "" {
		children.InputBytesBasis = old.InputBytesBasis
	} else if old.InputBytesBasis != "" && children.InputBytesBasis != old.InputBytesBasis {
		children.InputBytesBasis = "mixed"
	}
	children.Incomplete = true
	merged.ChildUsage, merged.UsageScope, merged.UsageStatus = &children, "run_and_children", "partial"
	merged.ModelCalls += children.ModelCalls - old.ModelCalls
	merged.SummaryCalls += children.SummaryCalls - old.SummaryCalls
	merged.CompletedCalls += children.CompletedCalls - old.CompletedCalls
	merged.FailedCalls += children.FailedCalls - old.FailedCalls
	merged.UsageCalls += children.UsageCalls - old.UsageCalls
	merged.Usage.InputTokens += children.Usage.InputTokens - old.Usage.InputTokens
	merged.Usage.OutputTokens += children.Usage.OutputTokens - old.Usage.OutputTokens
	merged.Usage.CacheReadTokens += children.Usage.CacheReadTokens - old.Usage.CacheReadTokens
	merged.Usage.CacheWriteTokens += children.Usage.CacheWriteTokens - old.Usage.CacheWriteTokens
	merged.ModelDurationMS += children.ModelDurationMS - old.ModelDurationMS
	merged.ModelTiming.Calls += children.ModelTiming.Calls - old.ModelTiming.Calls
	merged.ModelTiming.ProviderCalls += children.ModelTiming.ProviderCalls - old.ModelTiming.ProviderCalls
	merged.ModelTiming.QueueMS += children.ModelTiming.QueueMS - old.ModelTiming.QueueMS
	merged.ModelTiming.ProviderMS += children.ModelTiming.ProviderMS - old.ModelTiming.ProviderMS
	merged.TotalInputBytes += children.TotalInputBytes - old.TotalInputBytes
	if merged.InputBytesBasis == "" {
		merged.InputBytesBasis = children.InputBytesBasis
	} else if children.InputBytesBasis != "" && merged.InputBytesBasis != children.InputBytesBasis {
		merged.InputBytesBasis = "mixed"
	}
	return &merged
}

// Publishing and applying a result share the same failure boundary. Invalid
// output cannot become valid by replaying the saved Worker result; temporary
// delivery failures must leave that result available for same-run recovery.
func (m *Manager) resultDeliveryFailure(ctx context.Context, t *task, result protocol.Result, err error) (string, error) {
	if decisionStateChanged(context.Cause(ctx)) {
		// A cancelled HTTP call may wrap its heartbeat controlclient.ProtocolError. Reconcile
		// the receipt after joining the heartbeat before recording a failure.
		return "interrupted", context.Cause(ctx)
	}
	var pe *controlclient.ProtocolError
	if !errors.As(err, &pe) || pe.Status < 400 || pe.Status >= 500 || pe.Status == http.StatusRequestTimeout || pe.Status == http.StatusTooManyRequests {
		return "interrupted", err
	}
	status := "failed"
	result.Status, result.Retryable, result.FailureKind, result.Error = "failed", false, "invalid_output", err.Error()
	if decisionStateChanged(err) {
		result.FailureKind = "state_changed"
	} else if dependencyInvalidated(err) {
		status, result.FailureKind = "cancelled", "dependency_invalidated"
	}
	m.terminal(t, status, result)
	return status, err
}

func dependencyInvalidated(err error) bool {
	var failure *protocol.RPCError
	return errors.As(err, &failure) && failure.Status == 409 && failure.Code == board.CodeDependencyInvalidated
}

// Only roles whose entire write is bound to immutable input opt into early
// invalidation. Independent Execute work keeps its lease.
func immutableInputVersion(t *task) string {
	if t.Job.Kind == "reason" && t.Job.Decision != nil && t.Job.Decision.Version == 2 {
		return t.Job.Decision.StateVersion
	}
	if t.Job.Kind == "curate" {
		if t.Job.InputSnapshot != nil {
			return t.Job.InputSnapshot.StateVersion
		}
	}
	return ""
}

func decisionStateChanged(err error) bool {
	var failure *protocol.RPCError
	return errors.As(err, &failure) && failure.Status == 409 && failure.Code == board.CodeStateChanged
}

// A batch commits the graph and its execution result together. Prefer that
// receipt even if project completion cancelled the process before it replied.
func (m *Manager) controlCommitted(ctx context.Context, t *task) (bool, error) {
	if t.Job.Kind == "curate" {
		committed, err := m.curationCommitted(ctx, t)
		if err == nil && committed {
			t.committedAt.CompareAndSwap(0, time.Now().UnixNano())
		}
		return committed, err
	}
	if t.Job.Kind != "reason" || t.Job.Decision == nil || t.Job.Decision.Version != 2 {
		return false, nil
	}
	readCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	receipt, err := m.client.Decision(readCtx, t.Job.Graph.Project.ID, "receipt", nil, t.Lease)
	if err == nil && receipt.Committed {
		t.committedAt.CompareAndSwap(0, time.Now().UnixNano())
	}
	return receipt.Committed, err
}

func (m *Manager) decisionFinishAllowed(ctx context.Context, t *task) bool {
	committed, err := m.controlCommitted(ctx, t)
	if err != nil || !committed || time.Since(time.Unix(0, t.committedAt.Load())) >= decisionFinishGrace {
		return false
	}
	// A human stop or a new generation always overrides this delivery grace.
	readCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	input, err := m.client.Schedule(readCtx, t.Job.Graph.Project.ID, controlclient.ScheduleQuery{})
	return err == nil && input.Project.Generation == t.Job.Graph.Project.Generation && (input.Project.Status == "active" || input.Project.Status == "completed")
}

func (m *Manager) observeDecision(ctx context.Context, t *task, metrics *protocol.DecisionMetrics) {
	if metrics == nil {
		return
	}
	writeCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	if err := m.client.Observe(writeCtx, t.Job.Graph.Project.ID, t.Job.RunID, metrics, t.Lease); err != nil {
		slog.Warn("decision observation could not be saved", "project", t.Job.Graph.Project.ID, "run", t.Job.RunID, "error", err)
	}
}

const decisionFinishGrace = 10 * time.Second

func (m *Manager) curationCommitted(ctx context.Context, t *task) (bool, error) {
	readCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	receipt, err := m.client.CurationReceipt(readCtx, t.Job.Graph.Project.ID, t.Lease)
	var pe *controlclient.ProtocolError
	if errors.As(err, &pe) && pe.Status == 404 {
		return false, nil
	}
	if err == nil && receipt.Committed && receipt.ExecutionStatus != "succeeded" {
		return false, errors.New("committed curation requires a successful execution")
	}
	return receipt.Committed && err == nil, err
}
