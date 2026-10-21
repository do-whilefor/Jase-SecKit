package agent

import (
	"context"
	"errors"
	"time"
)

// RequestObservation describes a logical provider call. HTTP retries inside a
// provider and usage not returned by that provider are not observable here.
type RequestObservation struct {
	Kind       string       `json:"kind"`
	InputBytes int          `json:"input_bytes,omitempty"`
	InputBasis string       `json:"input_basis,omitempty"`
	DurationMS int64        `json:"duration_ms,omitempty"`
	Usage      *Usage       `json:"usage,omitempty"`
	Timing     *ModelTiming `json:"model_timing,omitempty"`
	Failed     bool         `json:"failed,omitempty"`
}

func (l *Loop) generateMeasured(ctx context.Context, messages []Message, defs []Definition, summaryTokens int) (Message, error) {
	// Providers may retain request buffers or reuse response storage. Neither
	// may become mutable transcript storage shared with this or another Loop.
	messages, defs = cloneMessages(messages), cloneDefinitions(defs)
	observation := RequestObservation{Kind: "turn"}
	if summaryTokens > 0 {
		observation.Kind = "summary"
	}
	if l.ObserveRequests {
		observation.InputBytes, _ = l.inputBytes(messages, defs)
		observation.InputBasis = "provider_request"
		l.emit(Event{Type: "model_call_start", Request: &observation})
	}
	started := time.Now()
	var message Message
	var err error
	if summaryTokens > 0 {
		message, err = l.Provider.GenerateSummary(ctx, messages, summaryTokens, nil)
	} else {
		message, err = l.Provider.Generate(ctx, messages, defs, l.emit)
	}
	if err == nil && summaryTokens == 0 && message.StopReason != "max_tokens" && message.StopReason != "length" {
		for _, block := range message.Content {
			if block.Type == "tool_use" && !objectArguments(block.Input) {
				err = &ModelError{Kind: ErrorToolArguments, Err: errors.New("tool arguments must be a JSON object")}
				break
			}
		}
	}
	if l.ObserveRequests {
		completed := observation
		completed.DurationMS, completed.Usage, completed.Failed = time.Since(started).Milliseconds(), message.Usage, err != nil
		if message.Timing != nil {
			timing := *message.Timing
			completed.Timing = &timing
		}
		l.emit(Event{Type: "model_call_end", Request: &completed})
	}
	return cloneMessage(message), err
}
