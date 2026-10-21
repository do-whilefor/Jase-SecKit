package bridge_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/board/model"
	"pwnmesh/internal/config"
	"pwnmesh/internal/docker"
	"pwnmesh/internal/launchbridge"
	"pwnmesh/internal/modelrpc"
	"pwnmesh/internal/modelwire"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/provider"
)

const requestID = "0123456789abcdef0123456789abcdef"

func job() protocol.Job {
	return protocol.Job{RunID: "run", Kind: "explore", GraphRPC: true,
		Graph: model.Graph{Project: model.Project{ID: "project", Generation: 3, OrchestrationVersion: 1}}}
}

func TestGraphBindingReplayAndRole(t *testing.T) {
	var calls int
	var responses []protocol.GraphResponse
	b := launchbridge.NewGraph(context.Background(), job(), func(ctx context.Context, bound protocol.Job, request protocol.GraphRequest) (any, error) {
		calls++
		if bound.RunID != "run" || bound.Graph.Project.ID != "project" || bound.Graph.Project.Generation != 3 {
			t.Fatalf("lost launch identity: %+v", bound)
		}
		return map[string]string{"value": "ok"}, nil
	}, func(ctx context.Context, response protocol.GraphResponse) error {
		if ctx.Err() != nil {
			t.Fatal(ctx.Err())
		}
		responses = append(responses, response)
		return nil
	})
	r := protocol.GraphRequest{RequestID: requestID, Op: "read_graph", Section: "facts"}
	for range 2 {
		if err := b.Handle(r); err != nil {
			t.Fatal(err)
		}
	}
	r.Section = "steps"
	if err := b.Handle(r); err != nil {
		t.Fatal(err)
	}
	if calls != 2 || responses[2].Failure == nil || !strings.Contains(responses[2].Failure.Detail, "reused") {
		t.Fatalf("changed replay reached handler: calls=%d replies=%+v", calls, responses)
	}
	r.RequestID = strings.Repeat("a", 32)
	r.Op, r.Section = "graph_action", ""
	r.Action = model.StateAction{Op: "goal", IdempotencyKey: "key", Payload: json.RawMessage(`{}`)}
	if err := b.Handle(r); err != nil || calls != 2 || responses[3].Failure == nil {
		t.Fatalf("Execute acquired Decide authority: %v, calls=%d", err, calls)
	}
	r.RequestID = "../invalid"
	if err := b.Handle(r); err == nil || len(responses) != 4 {
		t.Fatal("invalid response path identity was accepted")
	}
}

func TestGraphFailureBoundsAndCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var calls int
	var response protocol.GraphResponse
	b := launchbridge.NewGraph(ctx, job(), func(context.Context, protocol.Job, protocol.GraphRequest) (any, error) {
		calls++
		if calls == 1 {
			return nil, &protocol.RPCError{Code: "state_changed", Status: 409, Detail: "retry snapshot"}
		}
		return strings.Repeat("x", protocol.MaxGraphRPCBytes), nil
	}, func(ctx context.Context, out protocol.GraphResponse) error {
		deadline, ok := ctx.Deadline()
		if !ok || time.Until(deadline) > 5*time.Second || ctx.Err() != nil {
			t.Fatal("delivery escaped its launch or time budget")
		}
		response = out
		return nil
	})
	r := protocol.GraphRequest{RequestID: requestID, Op: "read_graph"}
	if err := b.Handle(r); err != nil || response.Failure == nil || response.Failure.Code != "state_changed" || response.Failure.Status != 409 {
		t.Fatalf("lost typed failure: %v, %+v", err, response)
	}
	raw, err := json.Marshal(response)
	if err != nil || strings.Contains(string(raw), `"error":`) || response.Failure.Detail != "retry snapshot" {
		t.Fatalf("graph failure did not use the typed envelope exclusively: %s, %v", raw, err)
	}
	r.RequestID = strings.Repeat("b", 32)
	if err := b.Handle(r); err != nil || response.Failure == nil || response.Failure.Code != "response_too_large" || response.Result != nil {
		t.Fatalf("oversized response escaped: %v, %+v", err, response.Failure)
	}
	r.Query = strings.Repeat("x", protocol.MaxGraphRPCBytes)
	if err := b.Handle(r); err == nil || calls != 2 {
		t.Fatal("oversized request reached handler")
	}
	r.Query = ""
	cancel()
	if err := b.Handle(r); !errors.Is(err, context.Canceled) || calls != 2 {
		t.Fatalf("canceled launch reached handler: %v", err)
	}
}

type session struct {
	generate func(context.Context, agent.Emit) (agent.Message, error)
	secrets  []string
}

func (s *session) Generate(ctx context.Context, _ []agent.Message, _ []agent.Definition, emit agent.Emit) (agent.Message, error) {
	return s.generate(ctx, emit)
}
func (s *session) GenerateSummary(ctx context.Context, _ []agent.Message, _ int, emit agent.Emit) (agent.Message, error) {
	return s.generate(ctx, emit)
}
func (s *session) InputBytes(messages []agent.Message, tools []agent.Definition) (int, error) {
	return (modelwire.RequestFormat{}).InputBytes(messages, tools)
}
func (s *session) CredentialValues() []string { return s.secrets }

func options(s *session, replies chan modelrpc.Response) launchbridge.ModelOptions {
	return launchbridge.ModelOptions{Job: job(), MaxTokens: 100, Timeout: time.Second,
		NewSession: func(string) launchbridge.ModelSession { return s },
		Deliver:    func(ctx context.Context, r modelrpc.Response) error { replies <- r; return ctx.Err() },
		Fail:       func(error) {},
	}
}

func receive(t *testing.T, replies <-chan modelrpc.Response) modelrpc.Response {
	t.Helper()
	select {
	case r := <-replies:
		return r
	case <-time.After(2 * time.Second):
		t.Fatal("bridge did not deliver")
		return modelrpc.Response{}
	}
}

func TestModelSessionBindingSummaryAndReplay(t *testing.T) {
	replies := make(chan modelrpc.Response, 2)
	s := &session{generate: func(context.Context, agent.Emit) (agent.Message, error) { return agent.Text("assistant", "ok"), nil }}
	opts := options(s, replies)
	identities := make(chan string, 1)
	opts.NewSession = func(id string) launchbridge.ModelSession { identities <- id; return s }
	b := launchbridge.NewModel(context.Background(), opts)
	defer b.Close()
	r := modelrpc.Request{RequestID: requestID, SessionID: "other"}
	if err := b.Start(r); err == nil {
		t.Fatal("foreign run accepted")
	}
	r.SessionID, r.SummaryTokens = "run:graph:node", 101
	if err := b.Start(r); err == nil {
		t.Fatal("summary allowance exceeded")
	}
	r.SummaryTokens = 1
	r.Tools = []agent.Definition{{Name: "tool"}}
	if err := b.Start(r); err == nil {
		t.Fatal("summary acquired tools")
	}
	r.Tools = nil
	if err := b.Start(r); err != nil {
		t.Fatal(err)
	}
	response := receive(t, replies)
	if response.Error != nil || response.Message.Text() != "ok" || <-identities != r.SessionID {
		t.Fatalf("lost child identity or response: %+v", response)
	}
	if err := b.Start(r); err == nil {
		t.Fatal("duplicate model request accepted")
	}
	b.Close()
	r.RequestID = strings.Repeat("a", 32)
	if err := b.Start(r); !errors.Is(err, context.Canceled) {
		t.Fatalf("closed launch accepted work: %v", err)
	}
}

func TestModelQueuedCancellationDoesNotCallProvider(t *testing.T) {
	replies := make(chan modelrpc.Response, 1)
	var calls atomic.Int32
	opts := options(&session{}, replies)
	opts.NewSession = func(string) launchbridge.ModelSession { calls.Add(1); return nil }
	opts.Admission = make(chan struct{}, 1)
	opts.Admission <- struct{}{}
	b := launchbridge.NewModel(context.Background(), opts)
	defer b.Close()
	if err := b.Start(modelrpc.Request{RequestID: requestID, SessionID: "run"}); err != nil {
		t.Fatal(err)
	}
	if err := b.Stop(requestID); err != nil {
		t.Fatal(err)
	}
	r := receive(t, replies)
	if r.Error == nil || !r.Error.Canceled || calls.Load() != 0 || r.Message.Timing == nil || r.Message.Timing.ProviderCalls != 0 {
		t.Fatalf("queued cancellation called provider or lost reply: %+v", r)
	}
}

func TestModelCloseCancelsActiveCallWithoutReply(t *testing.T) {
	replies, started := make(chan modelrpc.Response, 1), make(chan struct{})
	s := &session{generate: func(ctx context.Context, _ agent.Emit) (agent.Message, error) {
		close(started)
		<-ctx.Done()
		return agent.Message{}, ctx.Err()
	}}
	b := launchbridge.NewModel(context.Background(), options(s, replies))
	defer b.Close()
	if err := b.Start(modelrpc.Request{RequestID: requestID, SessionID: "run"}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("provider did not start")
	}
	b.Close()
	if len(replies) != 0 {
		t.Fatal("closed launch delivered a response")
	}
}

func TestModelCredentialAndErrorBoundary(t *testing.T) {
	for _, mode := range []string{"split_delta", "provider_error", "invalid_json"} {
		t.Run(mode, func(t *testing.T) {
			replies := make(chan modelrpc.Response, 1)
			s := &session{secrets: []string{"secret-token"}, generate: func(ctx context.Context, emit agent.Emit) (agent.Message, error) {
				message := agent.Message{Usage: &agent.Usage{InputTokens: 7}}
				switch mode {
				case "split_delta":
					emit(agent.Event{Text: "secret-"})
					emit(agent.Event{Text: "token"})
				case "provider_error":
					return message, &agent.ModelError{Kind: agent.ErrorTransport, Err: errors.New("https://provider.invalid/secret-token")}
				case "invalid_json":
					message.Content = []agent.Block{{Type: "tool_use", Input: json.RawMessage(`invalid`)}}
				}
				return message, nil
			}}
			b := launchbridge.NewModel(context.Background(), options(s, replies))
			defer b.Close()
			if err := b.Start(modelrpc.Request{RequestID: requestID, SessionID: "run"}); err != nil {
				t.Fatal(err)
			}
			r := receive(t, replies)
			raw, err := json.Marshal(r)
			if err != nil || strings.Contains(string(raw), "secret-") || r.Error == nil || r.Message.Usage == nil || r.Message.Usage.InputTokens != 7 || len(r.Events) != 0 {
				t.Fatalf("unsafe reply or lost usage: %s, %v", raw, err)
			}
			if mode == "provider_error" && r.Error.Kind != agent.ErrorTransport {
				t.Fatal("lost safe error classification")
			}
		})
	}
}

func TestDockerUsesInjectedModelFactoryBeforeTransport(t *testing.T) {
	c := docker.New(config.Container{Socket: "/unused"})
	defer c.Close()
	want := errors.New("factory sentinel")
	c.SetModelFactory(func(ctx context.Context, worker config.Worker, bound protocol.Job) (*provider.Client, error) {
		if bound.RunID != "run" || worker.Name != "worker" {
			t.Fatal("factory lost launch configuration")
		}
		return nil, want
	})
	if _, err := c.Run(context.Background(), config.Worker{Name: "worker"}, job()); !errors.Is(err, want) {
		t.Fatalf("factory was bypassed: %v", err)
	}
}

func TestCredentialScanChecksEscapesDuplicateKeysAndMalformedJSON(t *testing.T) {
	for _, raw := range []string{`{"value":"secret\u002dtoken"}`, `{"value":"secret-token","value":"safe"}`, `{"secret-token":true}`, `{broken`} {
		if !launchbridge.JSONContainsCredential([]byte(raw), "secret-token") {
			t.Fatalf("credential guard accepted %s", raw)
		}
	}
	if launchbridge.JSONContainsCredential([]byte(`{"value":"safe"}`), "secret-token") {
		t.Fatal("safe value rejected")
	}
}
