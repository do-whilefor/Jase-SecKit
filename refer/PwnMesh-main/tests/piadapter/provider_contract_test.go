package piadapter_test

import (
	"context"
	"errors"
	"strings"
	"testing"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelwire"
)

type contractProvider struct {
	providerFunc
	sizeErr      error
	summaryLimit int
	summaryBytes int
}

func (p *contractProvider) InputBytes(messages []agent.Message, tools []agent.Definition) (int, error) {
	if p.sizeErr != nil {
		return 0, p.sizeErr
	}
	return (modelwire.RequestFormat{}).InputBytes(messages, tools)
}

func (p *contractProvider) GenerateSummary(_ context.Context, messages []agent.Message, intLimit int, _ agent.Emit) (agent.Message, error) {
	p.summaryLimit = intLimit
	p.summaryBytes, _ = p.InputBytes(messages, nil)
	return agent.Text("assistant", "Retained summary."), nil
}

func TestPiProviderSizingFailureStopsBeforeModelCall(t *testing.T) {
	p := &contractProvider{sizeErr: errors.New("request encoding failed"), providerFunc: func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
		t.Fatal("request sizing failure reached the model")
		return agent.Message{}, nil
	}}
	loop := &agent.Loop{SessionDir: t.TempDir(), Provider: p}
	if _, err := loop.Run(context.Background(), "task"); err == nil || !strings.Contains(err.Error(), p.sizeErr.Error()) {
		t.Fatalf("request sizing silently fell back to an estimate: %v", err)
	}
}

func TestPiCompactionUsesProviderSummaryAllowance(t *testing.T) {
	directory := t.TempDir()
	history := []agent.Message{agent.Text("user", "Original assignment.")}
	for range 4 {
		history = append(history, agent.Text("assistant", strings.Repeat("retained evidence ", 300)), agent.Text("user", "Continue."))
	}
	history = append(history, agent.Text("assistant", "Recent observation."), agent.Text("user", "Check the result."), agent.Text("assistant", "Recent check completed."))
	var turnBytes int
	compacted := false
	observations := map[string]agent.RequestObservation{}
	p := &contractProvider{}
	p.providerFunc = func(_ context.Context, messages []agent.Message, tools []agent.Definition) (agent.Message, error) {
		turnBytes, _ = p.InputBytes(messages, tools)
		return agent.Text("assistant", "Done."), nil
	}
	loop := &agent.Loop{SessionDir: directory, Provider: p, Checkpoint: nativeCheckpoint(t, directory, history...),
		TaskPrompt: "Original assignment.", ContextTokens: 4000, ContextTargetTokens: 3000, SummaryMaxTokens: 1234,
		ObserveRequests: true, Emit: func(event agent.Event) {
			compacted = compacted || event.Type == "context_compacted"
			if event.Type == "model_call_end" && event.Request != nil {
				observations[event.Request.Kind] = *event.Request
			}
		}}
	if _, err := loop.Run(context.Background(), "Continue."); err != nil {
		t.Fatal(err)
	}
	if p.summaryLimit != 1234 || !compacted {
		t.Fatalf("compaction bypassed its provider allowance: limit=%d compacted=%v", p.summaryLimit, compacted)
	}
	for kind, want := range map[string]int{"summary": p.summaryBytes, "turn": turnBytes} {
		observation, ok := observations[kind]
		if !ok || want <= 0 || observation.InputBytes != want || observation.InputBasis != "provider_request" || observation.Failed {
			t.Fatalf("%s request observation lost provider sizing: %+v, want %d bytes", kind, observation, want)
		}
	}
}
