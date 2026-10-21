package modelwire_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelrpc"
	"pwnmesh/internal/modelwire"
	"pwnmesh/internal/provider"
)

func fixtureSource(api string) agent.ModelDescriptor {
	return agent.ModelDescriptor{ID: "fixture", API: api, Provider: "endpoint:fixture", Reasoning: true, MaxTokens: 1024, Input: []string{"text"}}
}

func TestThinkingReplayRequiresCompatibleSourceAndExplicitOpenAICapability(t *testing.T) {
	for _, protocol := range []string{"anthropic", "openai"} {
		api := "anthropic-messages"
		if protocol == "openai" {
			api = "openai-completions"
		}
		source := fixtureSource(api)
		for _, kind := range []string{"same", "model_changed", "api_changed", "endpoint_changed", "unknown", "disabled"} {
			t.Run(protocol+"/"+kind, func(t *testing.T) {
				origin := source
				message := agent.Message{Role: "assistant", Source: &origin, Content: []agent.Block{
					{Type: "thinking", Thinking: "private reasoning", Signature: "signed"},
					{Type: "redacted_thinking", Data: "opaque reasoning"},
					{Type: "text", Text: "Visible result"},
					{Type: "tool_use", ID: "call-1", Name: "echo", Input: json.RawMessage(`{"value":1}`)},
				}}
				switch kind {
				case "model_changed":
					origin.ID = "other"
				case "endpoint_changed":
					origin.Provider = "endpoint:other"
				case "api_changed":
					origin.API = "different-api"
				case "unknown":
					message.Source = nil
				}
				format := modelwire.RequestFormat{Protocol: protocol, Model: "fixture", MaxTokens: 1024, Source: source, ReasoningContent: kind != "disabled"}
				raw, err := format.Payload([]agent.Message{message}, nil, 1024)
				if err != nil {
					t.Fatal(err)
				}
				wantThinking := kind == "same" || protocol == "anthropic" && kind == "disabled"
				if strings.Contains(string(raw), "private reasoning") != wantThinking {
					t.Fatalf("unexpected thinking replay: %s", raw)
				}
				if strings.Contains(string(raw), "opaque reasoning") != (wantThinking && protocol == "anthropic") {
					t.Fatalf("unexpected signed reasoning replay: %s", raw)
				}
				if strings.Contains(string(raw), "model_source") || strings.Contains(string(raw), "endpoint:") {
					t.Fatalf("local model metadata leaked upstream: %s", raw)
				}
				if !strings.Contains(string(raw), "Visible result") || !strings.Contains(string(raw), "call-1") || len(message.Content) != 4 {
					t.Fatal("replay changed visible content, tool identity, or retained history")
				}
				if size, err := format.InputBytes([]agent.Message{message}, nil); err != nil || size != len(raw) {
					t.Fatalf("worker sizing differs from provider payload: %d, %d, %v", size, len(raw), err)
				}
			})
		}
	}
}

func TestOpenAIReasoningSurvivesJSONAndStreamingResponses(t *testing.T) {
	for _, stream := range []bool{false, true} {
		t.Run(fmt.Sprint(stream), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if stream {
					w.Header().Set("Content-Type", "text/event-stream")
					fmt.Fprint(w, "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"reasoning_content\":\"Retain \"}}]}\n\n")
					fmt.Fprint(w, "data: {\"choices\":[{\"index\":0,\"delta\":{\"reasoning_content\":\"reasoning\",\"content\":\"Answer\"},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n")
					return
				}
				w.Header().Set("Content-Type", "application/json")
				fmt.Fprint(w, `{"choices":[{"index":0,"message":{"role":"assistant","reasoning_content":"Retain reasoning","content":"Answer"},"finish_reason":"stop"}]}`)
			}))
			defer server.Close()
			client := &provider.Client{Protocol: "openai", BaseURL: server.URL, Token: "test-secret", Model: "fixture", MaxTokens: 1024, ReasoningContent: true}
			message, err := client.Generate(context.Background(), []agent.Message{agent.Text("user", "hello")}, nil, nil)
			if err != nil {
				t.Fatal(err)
			}
			if message.Source == nil || !message.Source.SameModel(client.ModelDescriptor()) || len(message.Content) != 2 || message.Content[0].Thinking != "Retain reasoning" || message.Text() != "Answer" {
				t.Fatalf("response lost reasoning or model source: %+v", message)
			}
			raw, err := client.RequestFormat().Payload([]agent.Message{message}, nil, 1024)
			if err != nil || !strings.Contains(string(raw), `"reasoning_content":"Retain reasoning"`) {
				t.Fatalf("reasoning could not replay: %s, %v", raw, err)
			}
			settings, err := json.Marshal(modelrpc.Settings{Model: client.Model, Descriptor: client.ModelDescriptor()})
			if err != nil || strings.Contains(string(settings), server.URL) || strings.Contains(string(settings), client.Token) {
				t.Fatalf("public model settings contain credentials or endpoint: %s, %v", settings, err)
			}
			other := &provider.Client{Protocol: client.Protocol, Model: client.Model, BaseURL: "https://other.invalid/v1"}
			if client.ModelDescriptor().SameModel(other.ModelDescriptor()) {
				t.Fatal("different endpoints share a model source")
			}
		})
	}
}

func TestModelSwitchOmitsThinkingOnlyAssistantWithoutChangingHistory(t *testing.T) {
	for _, protocol := range []string{"anthropic", "openai"} {
		t.Run(protocol, func(t *testing.T) {
			source := fixtureSource("anthropic-messages")
			origin := source
			origin.ID = "previous-model"
			messages := []agent.Message{
				agent.Text("user", "First question"),
				{Role: "assistant", Source: &origin, Content: []agent.Block{{Type: "thinking", Thinking: "private reasoning", Signature: "old-signature"}}},
				agent.Text("user", "Continue"),
			}
			format := modelwire.RequestFormat{Protocol: protocol, Model: source.ID, Source: source, MaxTokens: 1024}
			raw, err := format.Payload(messages, nil, 1024)
			if err != nil {
				t.Fatal(err)
			}
			var request struct {
				Messages []struct{ Role string } `json:"messages"`
			}
			if err = json.Unmarshal(raw, &request); err != nil {
				t.Fatal(err)
			}
			for _, message := range request.Messages {
				if message.Role == "assistant" {
					t.Fatalf("request contains a now-empty assistant: %s", raw)
				}
			}
			if !strings.Contains(string(raw), "Continue") || len(messages) != 3 || messages[1].Content[0].Thinking != "private reasoning" {
				t.Fatal("model switch damaged the original transcript or subsequent user message")
			}
		})
	}
}

func TestUnknownTargetSourceOmitsSignedReasoning(t *testing.T) {
	source := fixtureSource("anthropic-messages")
	message := agent.Message{Role: "assistant", Source: &source, Content: []agent.Block{
		{Type: "thinking", Thinking: "retained reasoning", Signature: "retained-signature"},
		{Type: "text", Text: "Answer"},
	}}
	format := modelwire.RequestFormat{Protocol: "anthropic", Model: source.ID, MaxTokens: 1024}
	raw, err := format.Payload([]agent.Message{message}, nil, 1024)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), "retained reasoning") || strings.Contains(string(raw), "retained-signature") || strings.Contains(string(raw), "model_source") || !strings.Contains(string(raw), "Answer") {
		t.Fatalf("unknown target source retained private reasoning or lost visible content: %s", raw)
	}
}

func TestReasoningContentCapabilityIsExplicit(t *testing.T) {
	for _, value := range []string{"", "true", "false", "invalid"} {
		env := map[string]string{"PWNMESH_MODEL_PROTOCOL": "openai", "OPENAI_MODEL": "fixture", "OPENAI_API_KEY": "test-secret", "PWNMESH_OPENAI_REASONING_CONTENT": value}
		client, err := provider.FromEnvironment(context.Background(), func(key string) string { return env[key] }, "")
		if value == "invalid" {
			if err == nil {
				t.Fatal("invalid capability was silently accepted")
			}
			continue
		}
		if err != nil || client.ReasoningContent != (value == "true") {
			t.Fatalf("unexpected capability %q: %+v, %v", value, client, err)
		}
	}
}
