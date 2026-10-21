package execution_test

import (
	"database/sql"
	"path/filepath"
	"strings"
	"testing"

	b "pwnmesh/internal/board"
)

const scheduleTrigger = "pwnmesh_schedule_invalidate_intents_update"

type storageSnapshot struct {
	Trigger, Ledger, Title, Cache string
	Counter                       int
}

func storageFixture(t *testing.T) (string, *sql.DB) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "board.db")
	store, err := b.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = store.Close(); err != nil {
		t.Fatal(err)
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	if _, err = db.Exec(`UPDATE pwnmesh_schema_migrations SET applied_at='original-ledger';
INSERT INTO projects(id,title,created_at) VALUES('proj_42','Retained project','2026-01-01T00:00:00Z');
UPDATE counters SET value=42 WHERE name='project';
INSERT INTO pwnmesh_schedule_cache(project_id,header,step_count) VALUES('proj_42','retained cache',0);`); err != nil {
		t.Fatal(err)
	}
	return path, db
}

func readStorageSnapshot(t *testing.T, db *sql.DB) storageSnapshot {
	t.Helper()
	var snapshot storageSnapshot
	for _, read := range []struct {
		query string
		value any
	}{
		{"SELECT sql FROM sqlite_master WHERE type='trigger' AND name='" + scheduleTrigger + "'", &snapshot.Trigger},
		{`SELECT group_concat(version||':'||name||':'||applied_at,'|') FROM (SELECT * FROM pwnmesh_schema_migrations ORDER BY version)`, &snapshot.Ledger},
		{"SELECT title FROM projects WHERE id='proj_42'", &snapshot.Title},
		{"SELECT header FROM pwnmesh_schedule_cache WHERE project_id='proj_42'", &snapshot.Cache},
		{"SELECT value FROM counters WHERE name='project'", &snapshot.Counter},
	} {
		if err := db.QueryRow(read.query).Scan(read.value); err != nil {
			t.Fatal(err)
		}
	}
	return snapshot
}

func TestCurrentStorageReopenPreservesTriggerAndLedger(t *testing.T) {
	path, db := storageFixture(t)
	definition := readStorageSnapshot(t, db).Trigger
	// Formatting is immaterial, and reopening must not rewrite valid SQL.
	definition = strings.Join(strings.Fields(definition), "\n  ")
	if _, err := db.Exec("DROP TRIGGER " + scheduleTrigger + ";" + definition); err != nil {
		t.Fatal(err)
	}
	before := readStorageSnapshot(t, db)
	store, err := b.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = store.Close(); err != nil {
		t.Fatal(err)
	}
	if after := readStorageSnapshot(t, db); after != before {
		t.Fatalf("current storage changed on reopen: before=%+v after=%+v", before, after)
	}
}

func TestUnsupportedScheduleTriggerIsRejectedWithoutRepair(t *testing.T) {
	for _, fixture := range []struct{ name, body string }{
		{"old", "DELETE FROM pwnmesh_schedule_cache WHERE project_id IN (NEW.project_id,OLD.project_id);"},
		{"unknown", "SELECT 1;"},
	} {
		t.Run(fixture.name, func(t *testing.T) {
			path, db := storageFixture(t)
			definition := "CREATE TRIGGER " + scheduleTrigger + " AFTER update ON intents BEGIN " + fixture.body + " END;"
			if _, err := db.Exec("DROP TRIGGER " + scheduleTrigger + ";" + definition + "UPDATE counters SET value=0 WHERE name='project';"); err != nil {
				t.Fatal(err)
			}
			before := readStorageSnapshot(t, db)
			store, err := b.Open(path)
			if store != nil {
				store.Close()
			}
			if err == nil || !strings.Contains(err.Error(), "inconsistent scheduling trigger definition") {
				t.Fatalf("unsupported trigger was not rejected: %v", err)
			}
			if after := readStorageSnapshot(t, db); after != before {
				t.Fatalf("rejected database was modified: before=%+v after=%+v", before, after)
			}
		})
	}
}
