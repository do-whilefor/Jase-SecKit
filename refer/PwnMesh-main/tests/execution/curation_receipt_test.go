package execution_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"path/filepath"
	"reflect"
	"testing"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
)

func TestCurationReceiptAndExecutionCommitTogether(t *testing.T) {
	for _, inconsistent := range []bool{false, true} {
		name := "current atomic receipt"
		if inconsistent {
			name = "inconsistent pending receipt"
		}
		t.Run(name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "board.db")
			store, err := b.Open(path)
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { store.Close() })
			var run b.Execution
			var action b.StateAction
			if err = store.Do(context.Background(), func(tx *b.Tx) error {
				graph, err := tx.CreateProject(b.ProjectInput{Title: "Curation", Origin: "Local fixture", Goal: "Verify atomic receipt"})
				if err != nil {
					return err
				}
				run = b.Execution{ProjectID: graph.Project.ID, ID: "curation", Namespace: "test", Backend: "docker", Kind: "curate", Lease: "docker@curation"}
				if _, err = tx.ClaimCurator(graph.Project.ID, run.Lease, "test"); err != nil {
					return err
				}
				run.Job, err = json.Marshal(protocol.Job{RunID: run.ID, Kind: "curate", WorkerType: "pi", GraphRPC: true, ResultContractVersion: 2, Graph: b.Graph{Project: graph.Project}, Workspace: "/workspace"})
				if err != nil {
					return err
				}
				prepared, err := execution.PrepareRun(tx, run, run.Fence())
				if err != nil {
					return err
				}
				run = prepared.Execution
				version, revision, err := b.CurationJobBoundary(run.Job)
				if err != nil {
					return err
				}
				payload, err := json.Marshal(b.CuratePayload{ThroughRevision: revision, Groups: []b.CurateGroup{}})
				action = b.StateAction{Op: "curate", IdempotencyKey: "curation-receipt", ExpectedVersion: version, Payload: payload}
				return err
			}); err != nil {
				t.Fatal(err)
			}
			var receipt b.StateActionResult
			if inconsistent {
				db, err := sql.Open("sqlite", path)
				if err != nil {
					t.Fatal(err)
				}
				var payload any
				if err := json.Unmarshal(action.Payload, &payload); err != nil {
					t.Fatal(err)
				}
				request, _ := json.Marshal(struct {
					Run, Op string
					Payload any
				}{run.Lease, "curate", payload})
				receipt = b.StateActionResult{Op: "curate", Committed: true}
				response, _ := json.Marshal(receipt)
				_, err = db.Exec("INSERT INTO pwnmesh_state_actions(project_id,idempotency_key,request,response) VALUES(?,?,?,?)", run.ProjectID, action.IdempotencyKey, string(request), string(response))
				db.Close()
				if err != nil {
					t.Fatal(err)
				}
			} else if err = store.Do(context.Background(), func(tx *b.Tx) error {
				var err error
				receipt, err = tx.StateAction(run.ProjectID, run.Fence(), action)
				return err
			}); err != nil {
				t.Fatal(err)
			}
			if err = store.Do(context.Background(), func(tx *b.Tx) error {
				current, err := tx.Execution(run.ProjectID, run.ID)
				if err != nil {
					return err
				}
				if !inconsistent && (!receipt.Committed || current.Status != "succeeded") {
					t.Fatalf("receipt and execution did not commit together: %+v, %s", receipt, current.Status)
				}
				replayed, replayErr := tx.StateAction(run.ProjectID, run.Fence(), action)
				if inconsistent {
					assertAPIError(t, replayErr, 409, "committed curation requires a successful execution")
				} else if replayErr != nil || !reflect.DeepEqual(replayed, receipt) {
					t.Fatalf("successful action replay was not idempotent: %+v, %v", replayed, replayErr)
				}
				status, applyErr := execution.Apply(tx, run.ProjectID, run.ID, run.Fence())
				if inconsistent {
					assertAPIError(t, applyErr, 409, "committed curation requires a successful execution")
				} else if applyErr != nil || status != "succeeded" {
					t.Fatalf("successful receipt delivery was not idempotent: %q, %v", status, applyErr)
				}
				after, err := tx.Execution(run.ProjectID, run.ID)
				if err == nil && !reflect.DeepEqual(current, after) {
					t.Fatal("receipt delivery changed its execution")
				}
				return err
			}); err != nil {
				t.Fatal(err)
			}
		})
	}
}
