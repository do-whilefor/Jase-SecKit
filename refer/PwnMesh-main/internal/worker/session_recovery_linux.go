//go:build linux

package worker

import (
	"context"
	"errors"
	"fmt"
	"pwnmesh/internal/agent"
)

// recover reuses durable results and receipts before admitting another request.
// Consumed allowances and the original identity/deadline are persisted first.
func (runtime *sessionRuntime) recover(ctx context.Context) (Result, bool, error) {
	j, o, state, journal, resuming := runtime.job, runtime.options, &runtime.state, runtime.journal, runtime.resuming
	save, emit := runtime.save, runtime.emit
	finish := func(r Result) (Result, bool, error) {
		result, err := runtime.finish(ctx, r)
		return result, true, err
	}
	if saved := state.Result; saved != nil && saved.Status == "success" {
		if checked := checkedResult(j, *saved); checked.Status != "success" {
			return Result{}, true, fmt.Errorf("invalid saved successful result: %s", checked.Error)
		}
		if saved.Retryable {
			return Result{}, true, errors.New("invalid saved successful result: terminal success cannot be retryable")
		}
		if last, ok := lastAssistant(state.History); ok && truncated(last) {
			return Result{}, true, errors.New("invalid saved successful result: assistant output was truncated")
		}
	}
	if j.Repair != nil {
		check, _, checkErr := inspectRepair(ctx, j)
		if checkErr != nil {
			return finish(Result{Type: "result", Status: "failed", FailureKind: "repair_check", Error: checkErr.Error()})
		}
		// A resumed successful result can only reuse its exact inspected bytes.
		if state.Result != nil && state.Result.Status == "success" && state.Result.RepairCheck != nil && state.Result.RepairCheck.SHA256 != check.SHA256 {
			return finish(Result{Type: "result", Status: "failed", FailureKind: "repair_stale", Error: "repair target changed after acceptance; main Agent must reassess", RepairCheck: &check})
		}
		if state.RepairCheck == nil {
			state.RepairCheck = &check
		}
		if check.Outcome == "stale" {
			return finish(Result{Type: "result", Status: "failed", FailureKind: "repair_stale", Error: "repair target SHA-256 changed and required checks still fail; main Agent must reassess", RepairCheck: &check})
		}
		if check.Satisfied && (state.Result == nil || state.Result.Retryable) {
			// Preserve the first execution decision across infrastructure recovery.
			// A prior model/tool run that fixed the target is never relabeled no-op.
			r, err := finishRepair(ctx, j, o.RunDir, Result{}, state.RepairCheck, o.Now())
			if err != nil {
				return finish(Result{Type: "result", Status: "failed", FailureKind: "repair_acceptance", Error: err.Error()})
			}
			return finish(r)
		}
	}
	runtime.infrastructureResume = false
	resumeFailureCause := ""
	if state.Result != nil {
		if state.Result.Retryable {
			runtime.infrastructureResume = true
			resumeFailureCause = infrastructureCauseKind(state.Result.FailureKind)
			state.Result = nil
		} else {
			return *state.Result, true, runtime.encoder.Encode(state.Result)
		}
	}
	if resuming {
		if state.RecoveryCount >= maxRunRecoveries {
			return finish(Result{Type: "result", Status: "failed", Conclude: state.Concluding, FailureKind: "recovery_exhausted", FailureCause: resumeFailureCause, Error: "same-run infrastructure recovery exhausted after 2 attempts"})
		}
		state.RecoveryCount++
		retained := journal.Recovery()
		if state.ContextCheckpoint == nil && retained.LastSequence > 0 {
			state.ContextCheckpoint = &agent.ContextCheckpoint{Version: agent.ContextCheckpointVersion}
		}
		if state.ContextCheckpoint != nil && state.ContextCheckpoint.LastSequence < retained.LastSequence {
			state.ContextCheckpoint.LastSequence = retained.LastSequence
		}
		emit(agent.Event{Type: "recovery", Text: fmt.Sprintf("same run recovery %d/%d; retained %d uncommitted log bytes; incomplete tail archive: %s", state.RecoveryCount, maxRunRecoveries, retained.Uncommitted, retained.PartialArchive)})
	}
	// The identity, budget and consumed recovery allowance precede any request.
	if err := save(state.History); err != nil {
		return Result{}, true, err
	}
	if o.Provider == nil {
		p, err := modelForJob(j, o, j.RunID)
		if err != nil {
			return Result{}, true, err
		}
		o.Provider = p
	}
	o.graphDeadline = state.ExecutionDeadline
	roles, err := newRoleRuntime(j, o, runtime.emit)
	if err != nil {
		return Result{}, true, err
	}
	roles.graph = graphRuntimeState{Version: state.GraphVersion, Conflict: state.DecisionConflict}
	runtime.options, runtime.roles = o, roles
	text, done, err := roles.recover(ctx, j, resuming)
	if err != nil {
		return Result{}, true, err
	}
	if done {
		return finish(Result{Type: "result", Status: "success", Text: text})
	}
	if roles.decision != nil || roles.curation != nil {
		runtime.endRepair()
	}
	return Result{}, false, nil
}
