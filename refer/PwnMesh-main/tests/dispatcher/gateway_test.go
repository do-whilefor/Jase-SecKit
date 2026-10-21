package dispatcher_test

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/graphgateway"
	"pwnmesh/internal/protocol"
)

type graphServer struct {
	controlclient.GraphServer
	identity board.ExecutionSummary
	decision board.DecisionReceipt
	curation controlclient.CurationReceipt
	failure  error
	calls    int
	lease    controlclient.Lease
}

func (s *graphServer) ExecutionIdentity(_ context.Context, project, run, namespace string) (board.ExecutionSummary, error) {
	if project != "project" || run != "run" || namespace != "ns" {
		return board.ExecutionSummary{}, errors.New("lookup did not use Job identity")
	}
	return s.identity, nil
}
func (s *graphServer) Decision(_ context.Context, _ string, _ string, _ *board.DecisionBatch, lease controlclient.Lease) (board.DecisionReceipt, error) {
	s.calls++
	s.lease = lease
	return s.decision, s.failure
}
func (s *graphServer) CurationReceipt(_ context.Context, _ string, lease controlclient.Lease) (controlclient.CurationReceipt, error) {
	s.calls++
	s.lease = lease
	return s.curation, s.failure
}

func graphFixture() (*graphServer, protocol.Job) {
	server := &graphServer{identity: board.ExecutionSummary{ProjectID: "project", ID: "run", Namespace: "ns", Kind: "reason", Lease: "worker@run", Generation: 3}}
	job := protocol.Job{RunID: "run", Kind: "reason", Graph: board.Graph{Project: board.Project{ID: "project", Generation: 3}}}
	return server, job
}

func TestGatewayRejectsChangedExecutionIdentity(t *testing.T) {
	for _, field := range []string{"project", "run", "namespace", "generation", "kind", "intent", "lease"} {
		t.Run(field, func(t *testing.T) {
			server, job := graphFixture()
			switch field {
			case "project":
				server.identity.ProjectID = "other"
			case "run":
				server.identity.ID = "other"
			case "namespace":
				server.identity.Namespace = "other"
			case "generation":
				server.identity.Generation++
			case "kind":
				server.identity.Kind = "curate"
			case "intent":
				server.identity.Intent = "step"
			case "lease":
				server.identity.Lease = ""
			}
			gateway := graphgateway.Gateway{Server: server, Namespace: "ns"}
			if _, err := gateway.Handle(context.Background(), job, protocol.GraphRequest{Op: "decision_commit"}); err == nil || server.calls != 0 {
				t.Fatalf("identity mismatch reached mutation: calls=%d, error=%v", server.calls, err)
			}
		})
	}
}

func TestGatewayCommitReceiptAndWake(t *testing.T) {
	for _, test := range []struct {
		name, op  string
		committed bool
		changes   int
		fail      bool
		wakes     int
	}{
		{"changed commit", "decision_commit", true, 2, false, 1},
		{"duplicate commit", "decision_commit", true, 0, false, 0},
		{"preview", "decision_preview", false, 2, false, 0},
		{"lost response", "decision_commit", true, 2, true, 0},
	} {
		t.Run(test.name, func(t *testing.T) {
			server, job := graphFixture()
			server.decision = board.DecisionReceipt{Committed: test.committed, ChangedActions: test.changes, Results: []board.StateActionResult{{ID: "fact", Result: json.RawMessage(`{"large":true}`)}}}
			if test.fail {
				server.failure = errors.New("delivery failed")
			}
			wakes := 0
			gateway := graphgateway.Gateway{Server: server, Namespace: "ns", Wake: func() { wakes++ }}
			value, err := gateway.Handle(context.Background(), job, protocol.GraphRequest{Op: test.op})
			if (err != nil) != test.fail || wakes != test.wakes {
				t.Fatalf("wakes=%d, error=%v", wakes, err)
			}
			if server.lease != (controlclient.Lease{Run: "worker@run", Kind: "reason"}) {
				t.Fatalf("unregistered lease used: %+v", server.lease)
			}
			receipt := value.(board.DecisionReceipt)
			if test.committed && len(receipt.Results) != 0 {
				t.Fatal("committed response retained large action results")
			}
			if !test.committed && len(receipt.Results) != 1 {
				t.Fatal("preview discarded action results")
			}
		})
	}
}

func TestGatewayMissingCurationReceiptIsNotFailure(t *testing.T) {
	server, job := graphFixture()
	job.Kind, server.identity.Kind = "curate", "curate"
	server.failure = &controlclient.ProtocolError{Status: 404}
	gateway := graphgateway.Gateway{Server: server, Namespace: "ns"}
	value, err := gateway.Handle(context.Background(), job, protocol.GraphRequest{Op: "curate_receipt"})
	if err != nil || value.(board.StateActionResult).Committed {
		t.Fatalf("missing receipt = %+v, %v", value, err)
	}
}
