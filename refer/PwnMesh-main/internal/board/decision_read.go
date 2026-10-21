package board

import (
	"database/sql"
	"encoding/json"
	"errors"
	"pwnmesh/internal/board/internal/sqlstore"
	"pwnmesh/internal/board/model"
)

// DecisionReadState pins a version 2 planner's detail reads to its last
// overview, or its registered input before the first refresh. Only one refreshed
// view is retained per recoverable execution, then released on completion or
// revocation. Writes still validate against current State.
func (t *Tx) DecisionReadState(current State, fence ExecutionFence, refresh bool) (State, error) {
	if fence.Run == "" || fence.Lease != "reason" {
		return current, nil
	}
	project := current.Graph.Project.ID
	id, raw, err := sqlstore.ExecutionInputByLease(t.transactionQueries, project, fence.Run, "reason")
	if errors.Is(err, sql.ErrNoRows) {
		return State{}, Err(403, "decision requires a registered input snapshot")
	}
	if err != nil {
		return State{}, err
	}
	version, err := DecisionJobVersion(raw)
	if err != nil {
		return State{}, err
	}
	if version == "" {
		return State{}, Err(422, "invalid decision snapshot binding")
	}
	var job model.JobInputBinding
	if err = json.Unmarshal(raw, &job); err != nil {
		return State{}, err
	}
	if job.Graph.Project.Generation != current.Graph.Project.Generation {
		return State{}, Err(409, "decision belongs to a previous project round")
	}
	if refresh {
		raw, err := json.Marshal(current)
		if err != nil {
			return State{}, err
		}
		err = sqlstore.SaveDecisionReadView(t.transactionQueries, project, id, DecisionStateVersion(current), raw)
		return current, err
	}
	version, raw, err = sqlstore.DecisionReadView(t.transactionQueries, project, id)
	if errors.Is(err, sql.ErrNoRows) {
		return t.ReadInputSnapshot(project, job.InputSnapshot.ID)
	}
	if err != nil {
		return State{}, err
	}
	var state State
	if err = json.Unmarshal(raw, &state); err != nil {
		return State{}, err
	}
	if state.Graph.Project.ID != project || state.Graph.Project.Generation != current.Graph.Project.Generation || DecisionStateVersion(state) != version {
		return State{}, errors.New("decision read view binding mismatch")
	}
	return state, nil
}
