package execution

import (
	"encoding/json"
	"errors"
	b "pwnmesh/internal/board"
	"pwnmesh/internal/protocol"
)

// ReadInput binds a decoded graph request to its transport-supplied identity.
// The use case neither opens nor commits a transaction.
type ReadInput struct {
	ProjectID, RunID string
	Fence            b.ExecutionFence
	Request          protocol.GraphRequest
}

func ReadSnapshot(t *b.Tx, input ReadInput) (any, error) {
	read := input.Request
	if err := protocol.ValidateGraphRequest(protocol.Job{}, read); err != nil {
		return nil, b.Err(422, err.Error())
	}
	e, err := t.Execution(input.ProjectID, input.RunID)
	if err != nil {
		return nil, err
	}
	if input.Fence != e.Fence() {
		return nil, b.Err(403, "Snapshot read requires its execution lease")
	}
	current, err := t.Load(e.ProjectID)
	if err != nil {
		return nil, err
	}
	if err = t.CheckExecutionRead(current, input.Fence); err != nil {
		return nil, err
	}
	var j protocol.Job
	if err = json.Unmarshal(e.Job, &j); err != nil {
		return nil, err
	}
	if err := protocol.ValidateSnapshotInput(j); err != nil {
		return nil, b.Err(409, err.Error())
	}
	state, err := t.ReadInputSnapshot(e.ProjectID, j.InputSnapshot.ID)
	if err != nil {
		return nil, err
	}
	page, err := protocol.GraphPage(state, read)
	if err != nil {
		var failure *protocol.RPCError
		if errors.As(err, &failure) {
			return nil, b.CodedErr(422, failure.Code, failure.Detail)
		}
		return nil, b.Err(422, err.Error())
	}
	return page, nil
}

// Bind live execution reads to the registered input and current project round
// before either endpoint selects updates or retained process traces.
func executionReadState(t *b.Tx, e b.Execution, fence b.ExecutionFence, read protocol.GraphRequest, roundError string) (protocol.Job, b.State, error) {
	var job protocol.Job
	var current b.State
	if err := json.Unmarshal(e.Job, &job); err != nil {
		return job, current, err
	}
	if err := protocol.ValidateSnapshotInput(job); err != nil {
		return job, current, b.Err(409, err.Error())
	}
	if err := protocol.ValidateGraphRequest(job, read); err != nil {
		return job, current, b.Err(422, err.Error())
	}
	current, err := t.State(e.ProjectID)
	if err != nil {
		return job, current, err
	}
	if err = t.CheckExecutionRead(current.Graph, fence); err != nil {
		return job, current, err
	}
	if job.Graph.Project.ID != e.ProjectID || job.Graph.Project.Generation != current.Graph.Project.Generation || job.RunID != e.ID || job.Kind != e.Kind {
		return job, current, b.Err(409, roundError)
	}
	return job, current, nil
}
