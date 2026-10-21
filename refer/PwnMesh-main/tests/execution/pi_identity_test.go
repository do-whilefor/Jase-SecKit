package execution_test

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"path/filepath"
	"testing"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/board/model"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
)

func reasonTemplate(t *testing.T, graph b.Graph, backend string) b.Execution {
	t.Helper()
	run := b.Execution{ProjectID: graph.Project.ID, ID: "pi-boundary", Namespace: "test", Backend: "docker", Kind: "reason", Lease: "docker@pi-boundary"}
	var err error
	run.Job, err = json.Marshal(protocol.Job{RunID: run.ID, Kind: run.Kind, WorkerType: backend, GraphRPC: true,
		ResultContractVersion: 2, Graph: b.Graph{Project: graph.Project}, Workspace: "/workspace", Budget: model.TaskBudget{MaxIntents: 2}})
	if err != nil {
		t.Fatal(err)
	}
	return run
}

func TestPreparationRejectsRetiredBackendBeforeSnapshot(t *testing.T) {
	for _, backend := range []string{"", "go", "agent", "mock"} {
		t.Run(backend, func(t *testing.T) {
			store, graph := storeProject(t)
			run := reasonTemplate(t, graph, backend)
			if err := store.Do(context.Background(), func(tx *b.Tx) error {
				if _, err := tx.ReasonLease(run.ProjectID, b.LeaseOperation{Op: "claim", Worker: run.Lease, Trigger: "test", Fence: run.Fence()}); err != nil {
					return err
				}
				state, err := tx.State(run.ProjectID)
				if err != nil {
					return err
				}
				raw, err := json.Marshal(state)
				if err != nil {
					return err
				}
				digest := sha256.Sum256(raw)
				_, err = execution.PrepareRun(tx, run, run.Fence())
				var api *b.APIError
				if !errors.As(err, &api) || api.Status != 422 {
					t.Fatalf("retired backend preparation = %v", err)
				}
				_, err = tx.InputSnapshotMetadata(run.ProjectID, hex.EncodeToString(digest[:]))
				assertAPIError(t, err, 404, "Input snapshot not found")
				_, err = tx.Execution(run.ProjectID, run.ID)
				assertAPIError(t, err, 404, "Execution not found")
				return nil // A caller may handle rejection and commit other work.
			}); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestRetiredBackendCannotResumeButSavedResultCanSettle(t *testing.T) {
	for _, pending := range []bool{false, true} {
		t.Run(map[bool]string{false: "live", true: "saved result"}[pending], func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "board.db")
			store, err := b.Open(path)
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { store.Close() })
			var graph b.Graph
			var run b.Execution
			if err := store.Do(context.Background(), func(tx *b.Tx) error {
				var err error
				graph, err = tx.CreateProject(b.ProjectInput{Title: "Pi identity", Origin: "Local fixture", Goal: "Verify recovery"})
				if err != nil {
					return err
				}
				run, err = prepareReason(tx, graph, "pi-boundary")
				if err != nil || !pending {
					return err
				}
				state, err := tx.State(run.ProjectID)
				if err != nil {
					return err
				}
				result, err := json.Marshal(protocol.Result{Status: "success", Text: `{"accepted":false,"reason":"Cannot proceed"}`, StateVersion: b.DecisionStateVersion(state)})
				if err != nil {
					return err
				}
				run, err = execution.ChangeStatus(tx, run.ProjectID, run.ID, run.Fence(), "result_pending", result)
				return err
			}); err != nil {
				t.Fatal(err)
			}
			// Model an existing database from before Pi-only registration. Its
			// preparation key deliberately matches the obsolete caller's template.
			template := reasonTemplate(t, graph, "go")
			canonical, err := json.Marshal(template)
			if err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(canonical)
			var job protocol.Job
			if err := json.Unmarshal(run.Job, &job); err != nil {
				t.Fatal(err)
			}
			job.WorkerType, job.PreparationKey = "go", hex.EncodeToString(digest[:])
			raw, err := json.Marshal(job)
			if err != nil {
				t.Fatal(err)
			}
			db, err := sql.Open("sqlite", path)
			if err != nil {
				t.Fatal(err)
			}
			_, err = db.Exec("UPDATE pwnmesh_executions SET job=? WHERE project_id=? AND id=?", raw, run.ProjectID, run.ID)
			db.Close()
			if err != nil {
				t.Fatal(err)
			}
			if err := store.Do(context.Background(), func(tx *b.Tx) error {
				_, err := execution.PrepareRun(tx, template, template.Fence())
				assertAPIError(t, err, 422, "worker_type must be pi")
				resumed, err := execution.Resume(tx, run.ProjectID, run.ID, run.Fence())
				if !pending {
					assertAPIError(t, err, 409, "Only Pi executions can resume model work")
					current, err := tx.Execution(run.ProjectID, run.ID)
					if err != nil {
						return err
					}
					if current.Resumes != 0 || current.Status != run.Status {
						t.Fatal("rejected continuation changed the execution")
					}
					_, err = execution.ChangeStatus(tx, run.ProjectID, run.ID, run.Fence(), "failed", json.RawMessage(`{"status":"failed"}`))
					return err
				}
				if err != nil || resumed.Resumes != 0 || resumed.Status != "result_pending" {
					t.Fatalf("saved-result resume = %+v, %v", resumed, err)
				}
				status, err := execution.Apply(tx, run.ProjectID, run.ID, run.Fence())
				if err != nil || status != "rejected" {
					t.Fatalf("saved result settlement = %q, %v", status, err)
				}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
		})
	}
}
