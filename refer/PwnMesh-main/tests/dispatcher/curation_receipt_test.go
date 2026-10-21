package dispatcher_test

import (
	"context"
	"strings"
	"testing"
	"time"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/dispatchrun"
	"pwnmesh/internal/protocol"
)

type curationReceiptServer struct {
	controlclient.Server
	status  string
	applied int
}

func (*curationReceiptServer) Resume(context.Context, string, string, controlclient.Lease) (board.Execution, error) {
	return board.Execution{Status: "running"}, nil
}
func (s *curationReceiptServer) CurationReceipt(context.Context, string, controlclient.Lease) (controlclient.CurationReceipt, error) {
	return controlclient.CurationReceipt{StateActionResult: board.StateActionResult{Op: "curate", Committed: true}, ExecutionStatus: s.status}, nil
}
func (s *curationReceiptServer) Apply(context.Context, string, string, controlclient.Lease) (string, error) {
	s.applied++
	return "succeeded", nil
}
func (*curationReceiptServer) Release(context.Context, string, controlclient.Lease) error { return nil }

func TestCurationReceiptRequiresAtomicallySucceededExecution(t *testing.T) {
	for _, status := range []string{"succeeded", "running", "result_pending"} {
		t.Run(status, func(t *testing.T) {
			server := &curationReceiptServer{status: status}
			runner := forbiddenRunner{started: make(chan struct{})}
			done := make(chan struct{}, 1)
			manager := dispatchrun.New(dispatchrun.Options{Server: server, Runner: runner, Interval: 30, MaxWorkers: 1, Wake: func() { done <- struct{}{} }})
			t.Cleanup(manager.Stop)
			assignment := dispatchrun.Assignment{Job: protocol.Job{RunID: "run", Kind: "curate", Graph: board.Graph{Project: board.Project{ID: "project"}}}, Lease: controlclient.Lease{Run: "worker@run", Kind: "curate"}}
			if err := manager.Resume(context.Background(), assignment); err != nil {
				t.Fatal(err)
			}
			select {
			case <-done:
			case <-time.After(time.Second):
				t.Fatal("receipt recovery did not finish")
			}
			completed := manager.Drain()
			if len(completed) != 1 {
				t.Fatalf("completion count = %d", len(completed))
			}
			if status == "succeeded" {
				if completed[0].Outcome != "success" || completed[0].Err != nil {
					t.Fatalf("committed receipt was not accepted: %+v", completed[0])
				}
			} else if completed[0].Outcome != "interrupted" || completed[0].Err == nil || !strings.Contains(completed[0].Err.Error(), "committed curation requires a successful execution") {
				t.Fatalf("inconsistent receipt was accepted: %+v", completed[0])
			}
			if server.applied != 0 {
				t.Fatalf("receipt recovery attempted %d settlement writes", server.applied)
			}
			select {
			case <-runner.started:
				t.Fatal("receipt recovery restarted model work")
			default:
			}
		})
	}
}
