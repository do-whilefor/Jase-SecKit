package sqlstore

import "pwnmesh/internal/board/model"

// Trace rows carry the registered Job for Board to validate before exposing
// any file capability. Stop on its first rejection without loading later Jobs.
func VisitTraceRuns(q Queries, project string, generation int64, offset, limit int, runID, workspace string, through *int64, visit func(model.TraceRun) error) error {
	query := `SELECT e.id,e.intent,e.status,e.job FROM pwnmesh_executions e WHERE e.project_id=? AND e.generation=? AND e.kind='explore' AND json_extract(e.job,'$.workspace')=?`
	args := []any{project, generation, workspace}
	if through != nil {
		// Terminal events bind curator discovery to its immutable input, even
		// when a source failed without publishing a Fact. Timestamps cannot
		// provide this boundary because registrations share second precision.
		query += ` AND e.status IN ('succeeded','failed','rejected','cancelled','retry_requested','retried') AND EXISTS (
			SELECT 1 FROM pwnmesh_state_events v WHERE v.project_id=e.project_id AND v.revision<=?
			AND json_extract(v.event,'$.op') IN ('step_completed','execution_failed')
			AND json_extract(v.event,'$.id')=e.intent AND json_extract(v.event,'$.run_id')=e.lease)`
		args = append(args, *through)
	}
	if runID != "" {
		query += " AND e.id=?"
		args = append(args, runID)
	}
	query += " ORDER BY e.rowid LIMIT ? OFFSET ?"
	args = append(args, limit, offset)
	rows, err := q.Query(query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		run := model.TraceRun{ProjectID: project, Generation: generation}
		var raw []byte
		if err := rows.Scan(&run.RunID, &run.StepID, &run.Status, &raw); err != nil {
			return err
		}
		run.RegisteredJob = raw
		if err := visit(run); err != nil {
			return err
		}
	}
	return rows.Err()
}
