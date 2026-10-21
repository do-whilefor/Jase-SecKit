package sqlstore

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"pwnmesh/internal/board/model"
)

const scheduleCacheSchema = `
CREATE TABLE pwnmesh_schedule_cache(
 project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
 header BLOB NOT NULL,step_count INTEGER NOT NULL CHECK(step_count>=0));
CREATE TABLE pwnmesh_schedule_steps(
 project_id TEXT NOT NULL REFERENCES pwnmesh_schedule_cache(project_id) ON DELETE CASCADE,
 position INTEGER NOT NULL CHECK(position>=0),data BLOB NOT NULL,
 PRIMARY KEY(project_id,position));`

// A revision alone misses leases, execution outcomes and asset support. Delete
// the disposable projection when its source rows change. Same-owner Execute
// heartbeats change no projected field; control heartbeats remain in the header.
var scheduleSources = []string{
	"projects", "facts", "intents", "intent_sources", "hints",
	"pwnmesh_state", "pwnmesh_fact_metadata", "pwnmesh_state_records", "pwnmesh_state_events",
	"pwnmesh_project_metadata", "pwnmesh_project_rounds", "pwnmesh_project_termination",
	"pwnmesh_project_orchestration", "pwnmesh_executions", "pwnmesh_revoked_runs",
	"pwnmesh_assets", "pwnmesh_asset_anchors",
}

func scheduleInvalidationObjects() []struct{ kind, name, table string } {
	var objects []struct{ kind, name, table string }
	for _, table := range scheduleSources {
		for _, op := range []string{"insert", "update", "delete"} {
			if table == "projects" && op != "update" {
				continue
			}
			objects = append(objects, struct{ kind, name, table string }{"trigger", "schedule_invalidate_" + table + "_" + op, table})
		}
	}
	return objects
}

func scheduleInvalidationSchema() string {
	var ddl strings.Builder
	for _, object := range scheduleInvalidationObjects() {
		op := object.name[strings.LastIndexByte(object.name, '_')+1:]
		column := "project_id"
		if object.table == "projects" {
			column = "id"
		}
		ref := "NEW." + column
		if op == "delete" {
			ref = "OLD." + column
		} else if op == "update" {
			ref += ",OLD." + column
		}
		if object.name == "schedule_invalidate_intents_update" {
			ddl.WriteString(intentScheduleTrigger())
		} else {
			fmt.Fprintf(&ddl, "CREATE TRIGGER pwnmesh_%s AFTER %s ON %s BEGIN DELETE FROM pwnmesh_schedule_cache WHERE project_id IN (%s); END;\n", object.name, op, object.table, ref)
		}
	}
	return ddl.String()
}

const intentScheduleTriggerName = "pwnmesh_schedule_invalidate_intents_update"

func intentScheduleTrigger() string {
	// Compare values, not UPDATE OF columns: renewal writes worker again.
	// Null-safe comparisons also retain invalidation on release/conclusion;
	// rowid participates in persisted ordering for equal creation times.
	condition := " WHEN OLD.worker IS NULL"
	for _, column := range []string{"rowid", "id", "project_id", "to_fact_id", "description", "creator", "worker", "created_at", "concluded_at"} {
		condition += " OR OLD." + column + " IS NOT NEW." + column
	}
	return "CREATE TRIGGER " + intentScheduleTriggerName + " AFTER update ON intents" + condition + " BEGIN DELETE FROM pwnmesh_schedule_cache WHERE project_id IN (NEW.project_id,OLD.project_id); END;\n"
}

// Existing stores must already use the current trigger. Validation never
// rewrites a retained schema definition, including known older definitions.
func validateScheduleTrigger(tx *sql.Tx) error {
	var definition string
	if err := tx.QueryRow("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name='intents'", intentScheduleTriggerName).Scan(&definition); err != nil {
		return err
	}
	normalize := func(sql string) string {
		return strings.TrimSuffix(strings.Join(strings.Fields(sql), " "), ";")
	}
	if normalize(definition) != normalize(intentScheduleTrigger()) {
		return fmt.Errorf("inconsistent scheduling trigger definition: %s", intentScheduleTriggerName)
	}
	return nil
}

func ScheduleHeader(q Queries, project string) (header []byte, count int, err error) {
	err = q.QueryRow("SELECT header,step_count FROM pwnmesh_schedule_cache WHERE project_id=?", project).Scan(&header, &count)
	return
}

// WritePaths are deliberately absent from public JSON, but admission still
// needs them after a cached page is loaded.
type storedScheduleStep struct {
	model.ScheduleStep
	WritePaths []string `json:"write_paths,omitempty"`
}

func ScheduleSteps(q Queries, project string, offset, limit int) ([]model.ScheduleStep, error) {
	rows, err := q.Query("SELECT data FROM pwnmesh_schedule_steps WHERE project_id=? AND position>=? ORDER BY position LIMIT ?", project, offset, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	steps := []model.ScheduleStep{}
	for rows.Next() {
		var raw []byte
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		var step storedScheduleStep
		if err := json.Unmarshal(raw, &step); err != nil {
			return nil, err
		}
		step.ScheduleStep.WritePaths = step.WritePaths
		steps = append(steps, step.ScheduleStep)
	}
	return steps, rows.Err()
}

func SaveSchedule(q Queries, project string, header []byte, steps []model.ScheduleStep) error {
	return Atomic(q, func() error {
		if _, err := q.Exec("DELETE FROM pwnmesh_schedule_cache WHERE project_id=?", project); err != nil {
			return err
		}
		if _, err := q.Exec("INSERT INTO pwnmesh_schedule_cache(project_id,header,step_count) VALUES(?,?,?)", project, header, len(steps)); err != nil {
			return err
		}
		for position, step := range steps {
			raw, err := json.Marshal(storedScheduleStep{ScheduleStep: step, WritePaths: step.WritePaths})
			if err != nil {
				return err
			}
			if _, err := q.Exec("INSERT INTO pwnmesh_schedule_steps(project_id,position,data) VALUES(?,?,?)", project, position, raw); err != nil {
				return err
			}
		}
		return nil
	})
}
