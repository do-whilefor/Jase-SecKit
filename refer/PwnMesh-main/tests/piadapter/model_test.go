package piadapter_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"pwnmesh/internal/agent"
)

type describedProvider struct{ providerFunc }

func (describedProvider) ModelDescriptor() agent.ModelDescriptor {
	return agent.ModelDescriptor{ID: "configured-model", API: "openai-completions", Provider: "endpoint-fingerprint", Reasoning: true, MaxTokens: 8192, Input: []string{"text"}}
}

func TestPiReceivesHostModelIdentity(t *testing.T) {
	loop := &agent.Loop{SessionDir: t.TempDir(), Provider: describedProvider{providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
		return agent.Text("assistant", "answer"), nil
	})}}
	if _, err := loop.Run(context.Background(), "task"); err != nil {
		t.Fatal(err)
	}
	var snapshot map[string]any
	if err := json.Unmarshal(loop.Checkpoint.PiSession, &snapshot); err != nil {
		t.Fatal(err)
	}
	for _, value := range []string{`"model":"configured-model"`, `"provider":"endpoint-fingerprint"`, `"api":"openai-completions"`} {
		if !strings.Contains(nativeTranscript(t, loop.Checkpoint), value) {
			t.Fatalf("Pi session lacks host model identity %s", value)
		}
	}
}
