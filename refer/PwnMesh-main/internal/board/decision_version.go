package board

import (
	"database/sql"
	"encoding/json"
	"errors"

	"pwnmesh/internal/board/internal/sqlstore"
	"pwnmesh/internal/board/model"
)

// DecisionStateVersion binds a plan to shared content rather than lease
// heartbeats or event counters. Copy slices before removing runtime metadata.
func DecisionStateVersion(state State) string { return model.DecisionStateVersion(state) }

// DecisionJobVersion validates the immutable input for a version 2 decision.
// A malformed or retired marker must never authorize decision reads or writes.
func DecisionJobVersion(raw json.RawMessage) (string, error) {
	var job model.DecisionJobBinding
	if err := json.Unmarshal(raw, &job); err != nil {
		return "", Err(422, "invalid decision job")
	}
	if job.Decision == nil {
		if job.Kind == "reason" {
			return "", Err(422, "decision requires protocol version 2")
		}
		return "", nil
	}
	if job.Decision.ClosureProtocol != 0 && (job.Decision.ClosureProtocol != 1 || job.Decision.Version != 2) {
		return "", Err(422, "unsupported closure protocol")
	}
	if job.Decision.Version != 2 {
		return "", Err(422, "decision requires protocol version 2")
	}
	ref := job.InputSnapshot
	if ref == nil || ref.Version != 1 || job.State != nil || job.Kind != "reason" || len(ref.ID) != 64 || len(ref.StateVersion) != 64 || ref.ProjectID != job.Graph.Project.ID || ref.Generation != job.Graph.Project.Generation || job.Decision.StateVersion != ref.StateVersion || len(job.Graph.Facts)+len(job.Graph.Intents)+len(job.Graph.Hints) != 0 {
		return "", Err(422, "invalid decision snapshot binding")
	}
	return ref.StateVersion, nil
}

// CheckDecisionStateVersion runs inside the same transaction as the write.
// Control writes require their registered input. Lease and source checks remain
// independent of the caller's expected version.
func (t *Tx) CheckDecisionStateVersion(state State, fence ExecutionFence, expected string) error {
	if fence.Lease == "curate" {
		_, raw, err := sqlstore.ExecutionInputByLease(t.transactionQueries, state.Graph.Project.ID, fence.Run, "curate")
		if err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				return Err(403, "curation requires a registered input snapshot")
			}
			return err
		}
		version, _, err := CurationJobBoundary(raw)
		if err != nil {
			return err
		}
		if expected != version {
			return Err(409, "curation input version does not match its registered snapshot")
		}
	}
	if fence.Lease == "reason" {
		_, raw, err := sqlstore.ExecutionInputByLease(t.transactionQueries, state.Graph.Project.ID, fence.Run, "reason")
		if errors.Is(err, sql.ErrNoRows) {
			return Err(403, "decision requires a registered input snapshot")
		}
		if err != nil {
			return err
		}
		if _, err := DecisionJobVersion(raw); err != nil {
			return err
		}
		if expected == "" {
			return Err(422, "decision write requires expected_version")
		}
	}
	if expected != "" && expected != DecisionStateVersion(state) {
		return CodedErr(409, CodeStateChanged, "state_changed: decision input is no longer current; read the graph before deciding again")
	}
	return nil
}
