package execution

import (
	"errors"
	b "pwnmesh/internal/board"
	"pwnmesh/internal/protocol"
)

// ReadGraph pins planner detail reads while writes still validate current state.
func ReadGraph(t *b.Tx, input ReadInput) (any, error) {
	read := input.Request
	if err := protocol.ValidateGraphRequest(protocol.Job{}, read); err != nil {
		return nil, b.Err(422, err.Error())
	}
	state, err := t.State(input.ProjectID)
	if err != nil {
		return nil, err
	}
	if err = t.CheckExecution(state.Graph, input.Fence); err != nil {
		return nil, err
	}
	// An unversioned overview explicitly refreshes a planner's read view.
	// Continuations and detail pages retain it even while other work publishes
	// evidence, so collecting a consistent input does not chase a moving graph.
	refresh := (read.Section == "" || read.Section == "overview") && read.ExpectedVersion == "" && read.ByteOffset == nil
	state, err = t.DecisionReadState(state, input.Fence, refresh)
	if err != nil {
		return nil, err
	}
	page, err := protocol.GraphPage(state, read)
	if err != nil {
		var failure *protocol.RPCError
		if errors.As(err, &failure) {
			return nil, b.CodedErr(failure.Status, failure.Code, failure.Detail)
		}
		return nil, b.Err(422, err.Error())
	}
	return page, nil
}
