// Package modelwire defines credential-free model requests and endpoint failures.
package modelwire

import (
	"encoding/json"
	"errors"
	"strings"

	"pwnmesh/internal/agent"
)

const System = "Work toward the assigned task using available tools. Distinguish confirmed facts from guesses. Follow the current request's output contract."
const DefaultModel = "deepseek-flash"
const DefaultReasoningEffort = "max"
const DefaultMaxTokens = 32768

// RequestFormat describes serialized model requests without transport or credentials.
type RequestFormat struct {
	Protocol         string
	Model            string
	MaxTokens        int
	ReasoningEffort  string
	Adaptive         bool
	Source           agent.ModelDescriptor
	ReasoningContent bool
}

func (p RequestFormat) InputBytes(messages []agent.Message, tools []agent.Definition) (int, error) {
	raw, err := p.Payload(messages, tools, p.MaxTokens)
	return len(raw), err
}

// Payload serializes the exact request body sent upstream.
func (p RequestFormat) Payload(messages []agent.Message, tools []agent.Definition, limit int) ([]byte, error) {
	if p.Protocol == "openai" {
		return p.openAIPayload(messages, tools, limit)
	}
	if p.Protocol != "" && p.Protocol != "anthropic" {
		return nil, errors.New("unsupported model protocol")
	}
	model := p.Model
	if model == "" {
		model = DefaultModel
	}
	if limit <= 0 {
		limit = DefaultMaxTokens
	}
	effort := p.ReasoningEffort
	if effort == "" {
		effort = DefaultReasoningEffort
	}
	switch effort {
	case "low", "high", "max":
	default:
		return nil, errors.New("reasoning effort must be low, high, or max")
	}
	system, conversation, err := splitSystem(messages)
	if err != nil {
		return nil, err
	}
	payload := struct {
		Model     string             `json:"model"`
		MaxTokens int                `json:"max_tokens"`
		System    string             `json:"system"`
		Messages  []agent.Message    `json:"messages"`
		Tools     []agent.Definition `json:"tools,omitempty"`
		Stream    bool               `json:"stream"`
		Thinking  struct {
			Type string `json:"type"`
		} `json:"thinking"`
		OutputConfig struct {
			Effort string `json:"effort"`
		} `json:"output_config"`
	}{Model: model, MaxTokens: limit, System: system, Messages: agent.WireHistory(p.replayMessages(conversation)), Tools: tools, Stream: true}
	// DeepSeek and GLM use enabled with effort. Kimi Coding and OpenRouter
	// require adaptive to express effort without a separate thinking budget.
	payload.Thinking.Type = "enabled"
	if p.Adaptive {
		payload.Thinking.Type = "adaptive"
	}
	payload.OutputConfig.Effort = effort
	return json.Marshal(payload)
}

// Reasoning can only replay with a known matching model and endpoint.
// Unknown provenance never authorizes replay of model-specific signatures.
func (p RequestFormat) replayMessages(messages []agent.Message) []agent.Message {
	result := make([]agent.Message, 0, len(messages))
	for _, message := range messages {
		if message.Role != "assistant" || message.Source != nil && message.Source.SameModel(p.Source) {
			result = append(result, message)
			continue
		}
		content := make([]agent.Block, 0, len(message.Content))
		for _, block := range message.Content {
			if block.Type != "thinking" && block.Type != "redacted_thinking" {
				content = append(content, block)
			}
		}
		if len(content) > 0 {
			message.Content = content
			result = append(result, message)
		}
	}
	return result
}

// Pi supplies its effective system prompt, including for compaction. Keep it
// separate from provider conversation messages; direct probes use the default.
func splitSystem(messages []agent.Message) (string, []agent.Message, error) {
	system := System
	conversation := make([]agent.Message, 0, len(messages))
	for _, message := range messages {
		if message.Role != "system" {
			conversation = append(conversation, message)
			continue
		}
		var text []string
		for _, block := range message.Content {
			if block.Type != "text" {
				return "", nil, errors.New("system messages require text content")
			}
			text = append(text, block.Text)
		}
		system = strings.Join(text, "\n")
	}
	return system, conversation, nil
}
