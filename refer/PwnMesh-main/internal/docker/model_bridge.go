package docker

import (
	"context"
	"encoding/json"
	"errors"
	"path"

	"pwnmesh/internal/config"
	"pwnmesh/internal/launchbridge"
	"pwnmesh/internal/modelrpc"
	"pwnmesh/internal/modelwire"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/provider"
)

// SetModelFactory selects the trusted source used when preparing each launch.
// A nil factory restores local environment configuration.
func (c *Client) SetModelFactory(factory func(context.Context, config.Worker, protocol.Job) (*provider.Client, error)) {
	c.graphMu.Lock()
	defer c.graphMu.Unlock()
	c.modelFactory = factory
}

func (c *Client) configuredModel(ctx context.Context, w config.Worker, j protocol.Job) (*provider.Client, error) {
	c.graphMu.RLock()
	factory := c.modelFactory
	c.graphMu.RUnlock()
	if factory != nil {
		return factory(ctx, w, j)
	}
	return provider.FromEnvironment(ctx, w.Getenv, j.Budget.ReasoningEffort)
}

func publicModelSettings(p *provider.Client) modelrpc.Settings {
	model := p.Model
	if model == "" {
		model = modelwire.DefaultModel
	}
	return modelrpc.Settings{Protocol: p.Protocol, Model: model, MaxTokens: p.MaxTokens, ReasoningEffort: p.ReasoningEffort, Timeout: p.Timeout, Adaptive: p.AdaptiveThinking(), Descriptor: p.ModelDescriptor(), ReasoningContent: p.ReasoningContent}
}

func modelWorkerEnv(w config.Worker, secrets ...string) ([]string, error) {
	values, err := w.ToolEnvironment()
	if err != nil {
		return nil, err
	}
	env := []string{"PWNMESH_MODEL_BRIDGE=dispatcher-v1"}
	for key, value := range values {
		if launchbridge.ContainsCredential(key+"="+value, secrets...) {
			return nil, errors.New("model credential is duplicated in the tool environment")
		}
		env = append(env, key+"="+value)
	}
	return env, nil
}

func (c *Client) modelDelivery(name, runDir string) func(context.Context, modelrpc.Response) error {
	return func(ctx context.Context, response modelrpc.Response) error {
		raw, err := json.Marshal(response)
		if err != nil {
			return err
		}
		target := path.Join(runDir, "model-response-"+response.RequestID+".json")
		return c.publish(ctx, name, target, raw)
	}
}

func modelSessions(p *provider.Client) func(string) launchbridge.ModelSession {
	return func(session string) launchbridge.ModelSession {
		return &provider.Client{AuthMode: p.AuthMode, TokenSource: p.TokenSource, Secrets: p.Secrets,
			Protocol: p.Protocol, BaseURL: p.BaseURL, Token: p.Token, Model: p.Model,
			MaxTokens: p.MaxTokens, ReasoningEffort: p.ReasoningEffort, Timeout: p.Timeout,
			ReasoningContent: p.ReasoningContent,
			Client:           p.Client, SessionID: session}
	}
}
