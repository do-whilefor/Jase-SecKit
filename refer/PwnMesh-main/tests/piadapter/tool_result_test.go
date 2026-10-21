package piadapter_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"pwnmesh/internal/agent"
)

func TestStructuredToolReceiptSurvivesBridgeAndFailure(t *testing.T) {
	calls := 0
	loop := &agent.Loop{SessionDir: t.TempDir(), Tools: []agent.Tool{{
		Definition: agent.Definition{Name: "probe", Schema: json.RawMessage(`{"type":"object"}`)},
		Execute: func(context.Context, json.RawMessage) (agent.ToolResult, error) {
			return agent.ToolResult{Text: "partial output", Details: json.RawMessage(`{"complete":false,"marker":"receipt-only"}`)}, errors.New("interrupted")
		},
	}}}
	loop.Provider = providerFunc(func(_ context.Context, messages []agent.Message, _ []agent.Definition) (agent.Message, error) {
		calls++
		if calls == 1 {
			return toolCall("typed-call", "probe"), nil
		}
		raw, _ := json.Marshal(messages)
		if strings.Contains(string(raw), "receipt-only") || !strings.Contains(string(raw), "partial output") || !strings.Contains(string(raw), "interrupted") {
			t.Fatalf("incorrect tool request projection: %s", raw)
		}
		return agent.Text("assistant", "done"), nil
	})
	if result, err := loop.Run(context.Background(), "task"); err != nil || result != "done" {
		t.Fatalf("result=%q error=%v", result, err)
	}
	if !strings.Contains(nativeTranscript(t, loop.Checkpoint), `"marker":"receipt-only"`) {
		t.Fatal("Pi lost structured receipt metadata")
	}
}
