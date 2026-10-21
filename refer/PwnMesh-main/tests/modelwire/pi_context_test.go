package modelwire_test

import (
	"encoding/json"
	"testing"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelwire"
)

func TestPiSystemPromptReachesBothProviderProtocols(t *testing.T) {
	for _, protocol := range []string{"anthropic", "openai"} {
		t.Run(protocol, func(t *testing.T) {
			format := modelwire.RequestFormat{Protocol: protocol, Model: "fixture", MaxTokens: 1024}
			messages := []agent.Message{
				agent.Text("system", "Summarize the conversation using Pi's compaction format."),
				agent.Text("user", "Retain the confirmed result."),
			}
			raw, err := format.Payload(messages, nil, 1024)
			if err != nil {
				t.Fatal(err)
			}
			var body struct {
				System   string `json:"system"`
				Messages []struct {
					Role    string          `json:"role"`
					Content json.RawMessage `json:"content"`
				} `json:"messages"`
			}
			if err = json.Unmarshal(raw, &body); err != nil {
				t.Fatal(err)
			}
			if protocol == "anthropic" {
				if body.System != messages[0].Text() || len(body.Messages) != 1 || body.Messages[0].Role != "user" {
					t.Fatalf("Pi system prompt was not lifted out of Anthropic messages: %s", raw)
				}
			} else {
				var system string
				if len(body.Messages) != 2 || body.Messages[0].Role != "system" {
					t.Fatalf("Pi system prompt was duplicated: %s", raw)
				}
				if err = json.Unmarshal(body.Messages[0].Content, &system); err != nil || system != messages[0].Text() {
					t.Fatalf("Pi system prompt was replaced: %s", raw)
				}
			}
			if size, err := format.InputBytes(messages, nil); err != nil || size != len(raw) {
				t.Fatalf("request sizing diverged: %d != %d, %v", size, len(raw), err)
			}
		})
	}
}
