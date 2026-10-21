package docker

import (
	"context"
	"encoding/json"
	"errors"
	"path"

	"pwnmesh/internal/launchbridge"
	"pwnmesh/internal/protocol"
)

func (c *Client) SetGraphHandler(handler func(context.Context, protocol.Job, protocol.GraphRequest) (any, error)) {
	c.graphMu.Lock()
	defer c.graphMu.Unlock()
	c.graphHandler = handler
}

func (c *Client) graphBridge(parent context.Context, name, runDir string, job protocol.Job) func(protocol.GraphRequest) error {
	handler := func(ctx context.Context, job protocol.Job, request protocol.GraphRequest) (any, error) {
		c.graphMu.RLock()
		current := c.graphHandler
		c.graphMu.RUnlock()
		if current == nil {
			return nil, errors.New("dispatcher has no graph handler")
		}
		return current(ctx, job, request)
	}
	deliver := func(ctx context.Context, response protocol.GraphResponse) error {
		raw, err := json.Marshal(response)
		if err != nil {
			return err
		}
		target := path.Join(runDir, "graph-response-"+response.RequestID+".json")
		return c.publish(ctx, name, target, raw)
	}
	return launchbridge.NewGraph(parent, job, handler, deliver).Handle
}
