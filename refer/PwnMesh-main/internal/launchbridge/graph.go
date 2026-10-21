package launchbridge

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"sync"
	"time"

	"pwnmesh/internal/protocol"
)

type GraphHandler func(context.Context, protocol.Job, protocol.GraphRequest) (any, error)
type GraphDelivery func(context.Context, protocol.GraphResponse) error

// Graph keeps job authority, request identity and response bounds independent of transport.
type Graph struct {
	ctx     context.Context
	job     protocol.Job
	handler GraphHandler
	deliver GraphDelivery
	mu      sync.Mutex
	seen    map[string][32]byte
}

func NewGraph(parent context.Context, job protocol.Job, handler GraphHandler, deliver GraphDelivery) *Graph {
	return &Graph{ctx: parent, job: job, handler: handler, deliver: deliver, seen: map[string][32]byte{}}
}

// Handle serializes requests from one launch, including replay bookkeeping.
func (b *Graph) Handle(request protocol.GraphRequest) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	parent, j, seen := b.ctx, b.job, b.seen
	if b.deliver == nil {
		return errors.New("graph bridge delivery is unavailable")
	}
	if !j.GraphRPC {
		return errors.New("graph bridge is disabled for this job")
	}
	if !protocol.ValidGraphRequestID(request.RequestID) {
		return errors.New("invalid graph request_id")
	}
	ctx, cancel := context.WithTimeout(parent, 20*time.Second)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return err
	}
	response := protocol.GraphResponse{RequestID: request.RequestID}
	raw, err := json.Marshal(request)
	envelope, envelopeErr := json.Marshal(protocol.GraphRequestEvent{Type: "graph_request", Request: request})
	if envelopeErr != nil || len(envelope) > protocol.MaxGraphRPCBytes {
		return errors.New("graph request exceeds 128 KiB")
	}
	digest := sha256.Sum256(raw)
	if err == nil {
		err = protocol.ValidateGraphRequest(j, request)
	}
	if previous, ok := seen[request.RequestID]; ok && previous != digest {
		err = errors.New("graph request_id reused for different input")
	}
	if len(seen) >= 4096 {
		err = errors.New("graph bridge request limit reached")
	}
	if err == nil {
		seen[request.RequestID] = digest
		handler := b.handler
		if handler == nil {
			err = errors.New("dispatcher has no graph handler")
		} else {
			var result any
			result, err = handler(ctx, j, request)
			if err == nil {
				response.Result, err = json.Marshal(result)
				if err == nil && request.Op == "graph_action" {
					response.Result, err = protocol.CompactGraphActionResult(response.Result)
				}
			}
		}
	}
	if err != nil {
		response.Failure = protocol.GraphFailure(err)
		response.Result = nil
	}
	cancel()
	raw, err = json.Marshal(response)
	if err != nil {
		return err
	}
	if len(raw) > protocol.MaxGraphRPCBytes {
		response.Result = nil
		response.Failure = &protocol.RPCError{Code: "response_too_large", Detail: "graph response exceeds 128 KiB; request a smaller page"}
	}
	// An operation timeout still needs a reply. Delivery has its own budget
	// within the Worker's 30-second wait, but never outlives the launch.
	delivery, stopDelivery := context.WithTimeout(parent, 5*time.Second)
	defer stopDelivery()
	if err := delivery.Err(); err != nil {
		return err
	}
	return b.deliver(delivery, response)
}
