// Package graphgateway binds Worker graph requests to registered executions.
// It knows the control plane contract, but neither scheduling state nor Docker.
package graphgateway

import (
	"context"
	"errors"
	"strings"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/protocol"
)

type Gateway struct {
	Server    controlclient.GraphServer
	Namespace string
	Wake      func()
}

func (g Gateway) wake() {
	if g.Wake != nil {
		g.Wake()
	}
}

func (g Gateway) Handle(ctx context.Context, job protocol.Job, request protocol.GraphRequest) (any, error) {
	// Registered identity, never model-generated fields, supplies authority.
	identity, err := g.Server.ExecutionIdentity(ctx, job.Graph.Project.ID, job.RunID, g.Namespace)
	if err != nil {
		return nil, err
	}
	intent := ""
	if job.Intent != nil {
		intent = job.Intent.ID
	}
	if identity.ProjectID != job.Graph.Project.ID || identity.Generation != job.Graph.Project.Generation || identity.ID != job.RunID || identity.Namespace != g.Namespace || identity.Kind != job.Kind || identity.Intent != intent || identity.Lease == "" {
		return nil, errors.New("graph request has no registered execution")
	}
	lease := controlclient.Lease{Run: identity.Lease, Kind: identity.Kind, Intent: identity.Intent}
	project := job.Graph.Project.ID
	switch request.Op {
	case "curate_receipt":
		receipt, err := g.Server.CurationReceipt(ctx, project, lease)
		var failure *controlclient.ProtocolError
		if errors.As(err, &failure) && failure.Status == 404 {
			return board.StateActionResult{}, nil
		}
		result := receipt.StateActionResult
		result.Result = nil
		return result, err
	case "decision_preview", "decision_commit", "decision_receipt":
		op := strings.TrimPrefix(request.Op, "decision_")
		result, err := g.Server.Decision(ctx, project, op, request.Batch, lease)
		if err == nil && op == "commit" && result.Committed && result.ChangedActions > 0 {
			g.wake()
		}
		// Commit/recovery need compact acknowledgements; previews retain review.
		if result.Committed || result.CompletionReview != nil {
			result.Results = nil
		}
		return result, err
	case "read_graph", "read_snapshot", "read_updates", "read_trace_runs":
		return g.Server.ReadGraph(ctx, project, job.RunID, request, lease)
	case "graph_action":
		result, err := g.Server.GraphAction(ctx, project, request.Action, lease)
		if err == nil && !result.Unchanged {
			g.wake()
		}
		return result, err
	default:
		return nil, errors.New("unknown graph request")
	}
}
