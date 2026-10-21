package dispatcher

import (
	"context"

	"pwnmesh/internal/graphgateway"
	"pwnmesh/internal/protocol"
)

func (s *Scheduler) configureGraphHandler() {
	setter, ok := s.Runner.(interface {
		SetGraphHandler(func(context.Context, protocol.Job, protocol.GraphRequest) (any, error))
	})
	if !ok {
		return
	}
	setter.SetGraphHandler(func(ctx context.Context, job protocol.Job, request protocol.GraphRequest) (any, error) {
		gateway := graphgateway.Gateway{Server: s.Client, Namespace: s.namespace(), Wake: s.wake}
		return gateway.Handle(ctx, job, request)
	})
}
