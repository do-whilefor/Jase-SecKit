package execution

import b "pwnmesh/internal/board"

// ReadUpdates selects events and source versions from the same transaction.
func ReadUpdates(t *b.Tx, input ReadInput) (*b.ExecuteUpdates, error) {
	read := input.Request
	e, err := t.Execution(input.ProjectID, input.RunID)
	if err != nil {
		return nil, err
	}
	if input.Fence != e.Fence() {
		return nil, b.Err(403, "Updates read requires its execution lease")
	}
	if e.Kind == "reason" || e.Intent == "" || !e.Pending() || e.Status == "result_pending" {
		return nil, b.Err(409, "Updates require an active Execute run")
	}
	job, current, err := executionReadState(t, e, input.Fence, read, "Updates input belongs to another execution or project round")
	if err != nil {
		return nil, err
	}
	original, err := t.ReadInputSnapshot(e.ProjectID, job.InputSnapshot.ID)
	if err != nil {
		return nil, err
	}
	base := b.ExecuteUpdateCursor{ProjectID: e.ProjectID, Generation: job.Graph.Project.Generation, StepID: e.Intent, RunID: e.ID}
	if original.Graph.Project.ID != base.ProjectID || original.Graph.Project.Generation != base.Generation {
		return nil, b.Err(409, "Updates original input identity mismatch")
	}
	base.Revision = original.Revision
	var sources []string
	for _, step := range original.Steps {
		if step.ID == e.Intent {
			sources = step.From
			break
		}
	}
	if len(sources) == 0 {
		return nil, b.Err(409, "Updates original input has no Step sources")
	}
	cursor := base
	if read.Updates != nil {
		cursor = *read.Updates
		if cursor.ProjectID != base.ProjectID || cursor.Generation != base.Generation || cursor.StepID != base.StepID || cursor.RunID != base.RunID || cursor.Revision < base.Revision || cursor.Revision > current.Revision {
			return nil, b.Err(422, "Updates cursor does not match the registered input")
		}
	}
	changes, err := t.StateChanges(e.ProjectID, cursor.Revision, current.Revision)
	if err != nil {
		return nil, err
	}
	updates, err := b.BuildExecuteUpdates(current, cursor, sources, changes, b.MaxExecuteUpdateBytes)
	if err != nil {
		return nil, b.Err(422, err.Error())
	}
	return updates, nil
}
