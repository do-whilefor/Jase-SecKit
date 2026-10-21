package piadapter_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"pwnmesh/internal/agent"
)

func TestFailedAttemptIsRetainedWithoutReplayingPartialTools(t *testing.T) {
	loop := &agent.Loop{SessionDir: t.TempDir(), Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
		message := toolCall("unexecuted", "probe")
		message.Content = append(message.Content, agent.Block{Type: "text", Text: "partial response"})
		return message, &agent.ModelError{Kind: agent.ErrorTransport, Err: errors.New("interrupted response")}
	})}
	_, err := loop.Run(context.Background(), "task")
	var failure *agent.ModelError
	if !errors.As(err, &failure) || failure.Kind != agent.ErrorTransport {
		t.Fatalf("lost transport error: %v", err)
	}
	if loop.Checkpoint == nil || !strings.Contains(nativeTranscript(t, loop.Checkpoint), "partial response") ||
		!strings.Contains(nativeTranscript(t, loop.Checkpoint), "context_edit") {
		t.Fatal("failed response and native omission were not retained")
	}
	raw, err := json.Marshal(loop.History)
	if err != nil || strings.Contains(string(raw), "partial response") {
		t.Fatalf("failed attempt entered accepted history: %s, %v", raw, err)
	}
	loop.Provider = providerFunc(func(_ context.Context, messages []agent.Message, _ []agent.Definition) (agent.Message, error) {
		raw, _ := json.Marshal(messages)
		if strings.Contains(string(raw), "partial response") || strings.Contains(string(raw), "unexecuted") {
			t.Fatalf("failed attempt entered recovery request: %s", raw)
		}
		return agent.Text("assistant", "recovered"), nil
	})
	if result, err := loop.Run(context.Background(), ""); err != nil || result != "recovered" {
		t.Fatalf("result=%q error=%v", result, err)
	}
}
