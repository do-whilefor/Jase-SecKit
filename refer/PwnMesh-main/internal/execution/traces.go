package execution

import (
	b "pwnmesh/internal/board"
	"pwnmesh/internal/protocol"
)

type TracePage struct {
	Items      []b.TraceRun `json:"items"`
	NextOffset *int         `json:"next_offset,omitempty"`
}

// ReadTraces authorizes retained process reads from the registered input.
func ReadTraces(t *b.Tx, input ReadInput) (TracePage, error) {
	read := input.Request
	e, err := t.Execution(input.ProjectID, input.RunID)
	if err != nil {
		return TracePage{}, err
	}
	if input.Fence != e.Fence() {
		return TracePage{}, b.Err(403, "Trace read requires its execution lease")
	}
	if !e.Pending() || e.Status == "result_pending" {
		return TracePage{}, b.Err(409, "Trace read requires an active execution")
	}
	job, _, err := executionReadState(t, e, input.Fence, read, "Trace read belongs to another execution or project round")
	if err != nil {
		return TracePage{}, err
	}
	limit := read.Limit
	if limit == 0 {
		limit = 10
	}
	runID := ""
	if len(read.IDs) == 1 {
		runID = read.IDs[0]
	}
	var through *int64
	if job.Kind == "curate" {
		revision := job.CurationRevision()
		through = &revision
	}
	items, err := t.TraceRuns(e.ProjectID, job.Graph.Project.Generation, read.Offset, limit, runID, job.Workspace, through)
	if err != nil {
		return TracePage{}, err
	}
	for i := range items {
		items[i], err = protocol.BindTraceRun(items[i])
		if err != nil {
			return TracePage{}, err
		}
	}
	page := TracePage{Items: items}
	if runID == "" && len(items) == limit {
		next := read.Offset + len(items)
		page.NextOffset = &next
	}
	return page, nil
}
