package agent

import (
	"context"
	"sync"
	"time"
)

type Loop struct {
	Provider Provider
	// Directory binds a new Pi session to the application's task workspace.
	Directory string
	// SessionDir stores Pi's canonical append-only transcript.
	SessionDir string
	Tools      []Tool
	History    []Message
	Emit       Emit
	// SaveState commits application state with its Pi checkpoint. History is a
	// derived request view; original messages remain in the native transcript.
	SaveState  func([]Message, *ContextCheckpoint) error
	Checkpoint *ContextCheckpoint
	// A nonempty reason both hides tools and rejects calls. The runtime owns
	// the policy and its explanation; Loop has no application-specific phases.
	ToolsDisabledReason string
	// Task and ordered runtime instructions survive every compaction verbatim.
	TaskPrompt         string
	PinnedInstructions []string
	// ContextData retains bounded runtime task data verbatim during compaction.
	// Callers persist and restore it separately from task and phase instructions.
	ContextData []string
	// ContextDataPrefixes identifies runtime-owned text snapshots superseded by
	// current ContextData. Only single-text user messages match; originals remain
	// in the transcript. Empty prefixes are ignored. Callers supply trusted values.
	ContextDataPrefixes []string
	// BeforeRequest prepares external task data at a settled history boundary,
	// before compaction and each normal model request. Summary requests and an
	// immediate context-overflow retry reuse that boundary without calling it.
	// A non-nil replacement context bounds subsequent work.
	BeforeRequest func(context.Context, *Loop) (context.Context, error)
	// OnTurnEnd runs at a settled model/tool boundary. A returned prompt keeps
	// the same session running; a replacement context bounds subsequent turns.
	OnTurnEnd func(context.Context, *Loop, Message) (context.Context, string, error)
	// StopResult lets the runtime end immediately after an authoritative tool
	// commit. Remaining calls are settled without executing more side effects.
	StopResult func() (string, bool)
	// A byte budget is an approximation, not a provider token count.
	ContextBytes int
	// ContextTokens is an optional input allowance after reserving output space.
	// Token estimates are labelled estimates; ContextBytes remains a hard cap.
	ContextTokens int
	// ContextTargetTokens bounds the rebuilt request after compaction without
	// changing its trigger. Zero derives the target from the trigger budget.
	ContextTargetTokens int
	SummaryMaxTokens    int
	ObserveRequests     bool
	mu                  sync.Mutex
	stateOwned          bool
	bridgeContext       context.Context
	sessionRevision     uint64
}

func (l *Loop) emit(e Event) {
	if l.Emit != nil {
		l.mu.Lock()
		defer l.mu.Unlock()
		switch e.Type {
		case "agent_start", "agent_end", "turn_start", "turn_end", "model_call_start", "model_call_end", "tool_start", "tool_end":
			e.At = time.Now().UTC().Format(time.RFC3339Nano)
		}
		if e.Message != nil {
			message := cloneMessage(*e.Message)
			e.Message = &message
		}
		if e.Request != nil {
			request := *e.Request
			request.Usage = cloneUsage(request.Usage)
			e.Request = &request
		}
		if e.Compaction != nil {
			record := *e.Compaction
			record.Usage = cloneUsage(record.Usage)
			record.View = cloneMessages(record.View)
			e.Compaction = &record
		}
		l.Emit(e)
	}
}
