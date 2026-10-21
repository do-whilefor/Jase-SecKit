package agent

import (
	"encoding/json"
	"errors"
	"fmt"
)

const ContextCheckpointVersion = 2

// ContextCheckpoint atomically binds application state to a Pi transcript.
type ContextCheckpoint struct {
	// PiSession references the committed prefix of Pi's native JSONL transcript.
	PiSession    json.RawMessage `json:"pi_session,omitempty"`
	Version      int             `json:"version"`
	LastSequence uint64          `json:"last_sequence"`
}

// CompactionRecord is a self-contained evidence projection of a Pi compaction.
type CompactionRecord struct {
	Version              int    `json:"version"`
	ID                   uint64 `json:"id"`
	PreviousID           uint64 `json:"previous_id,omitempty"`
	SourceStart          uint64 `json:"source_start"`
	SourceEnd            uint64 `json:"source_end"`
	AtSequence           uint64 `json:"at_sequence"`
	FirstKeptSequence    uint64 `json:"first_kept_sequence,omitempty"`
	Summary              string `json:"summary"`
	BeforeBytes          int    `json:"before_bytes"`
	AfterBytes           int    `json:"after_bytes"`
	BeforeTokensEstimate int    `json:"before_tokens_estimate"`
	AfterTokensEstimate  int    `json:"after_tokens_estimate"`
	TokenBasis           string `json:"token_basis"`
	Usage                *Usage `json:"usage,omitempty"`
	Reason               string `json:"reason"`
	Status               string `json:"status"`
	// View makes this event self-contained for request-view replay even after
	// later compactions. Sequence 0 denotes synthetic pinned/summary messages.
	View []Message `json:"view"`
}

func (l *Loop) initCheckpoint() error {
	if l.Checkpoint != nil {
		if l.Checkpoint.Version != ContextCheckpointVersion {
			return errors.New("unsupported context checkpoint version")
		}
	} else {
		l.Checkpoint = &ContextCheckpoint{Version: ContextCheckpointVersion}
	}
	if len(l.History) > 0 && len(l.Checkpoint.PiSession) == 0 {
		return errors.New("conversation history requires a canonical Pi session")
	}
	return nil
}

func (l *Loop) definitions() []Definition {
	var defs []Definition
	if l.ToolsDisabledReason == "" {
		for _, t := range l.Tools {
			defs = append(defs, t.Definition)
		}
	}
	return defs
}

// WireHistory deliberately drops local usage, sequence and stop metadata.
func WireHistory(messages []Message) []Message {
	result := make([]Message, len(messages))
	for i, m := range messages {
		result[i] = Message{Role: m.Role, Content: m.Content}
		copied := false
		for n, b := range m.Content {
			if b.Type != "tool_use" || objectArguments(b.Input) {
				continue
			}
			// Retained evidence is immutable. Normalize only the request view,
			// retaining tool IDs/results and never replaying historical effects.
			if !copied {
				result[i].Content = append([]Block(nil), m.Content...)
				copied = true
			}
			result[i].Content[n].Input = json.RawMessage(`{}`)
			result[i].Content = append(result[i].Content, Block{Type: "text", Text: fmt.Sprintf("Historical tool arguments for %q were invalid; {} is a protocol placeholder. Use the original transcript for execution evidence.", b.ID)})
		}
	}
	return result
}

func (l *Loop) inputBytes(messages []Message, defs []Definition) (int, error) {
	if l.Provider == nil {
		return 0, errors.New("missing model provider")
	}
	return l.Provider.InputBytes(cloneMessages(messages), cloneDefinitions(defs))
}
