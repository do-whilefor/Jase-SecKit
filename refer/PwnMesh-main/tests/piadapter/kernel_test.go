package piadapter_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"pwnmesh/internal/agent"
)

type providerFunc func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error)

func (provider providerFunc) Generate(ctx context.Context, messages []agent.Message, tools []agent.Definition, _ agent.Emit) (agent.Message, error) {
	return provider(ctx, messages, tools)
}

func (provider providerFunc) GenerateSummary(ctx context.Context, messages []agent.Message, _ int, _ agent.Emit) (agent.Message, error) {
	return provider(ctx, messages, nil)
}

func (provider providerFunc) InputBytes(messages []agent.Message, tools []agent.Definition) (int, error) {
	raw, err := json.Marshal(struct {
		Messages []agent.Message    `json:"messages"`
		Tools    []agent.Definition `json:"tools"`
	}{messages, tools})
	return len(raw), err
}

func toolCall(id, name string) agent.Message {
	return agent.Message{Role: "assistant", StopReason: "tool_use",
		Content: []agent.Block{{Type: "tool_use", ID: id, Name: name, Input: json.RawMessage(`{}`)}}}
}

func testTool(name string, execute func(context.Context, json.RawMessage) (string, error)) agent.Tool {
	return agent.Tool{Definition: agent.Definition{Name: name, Description: name,
		Schema: json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)}, Execute: agent.TextExecutor(execute)}
}

func hasText(messages []agent.Message, text string) bool {
	for _, message := range messages {
		if strings.Contains(message.Text(), text) {
			return true
		}
	}
	return false
}

func nativeCheckpoint(t *testing.T, directory string, messages ...agent.Message) *agent.ContextCheckpoint {
	t.Helper()
	raw, err := json.Marshal(map[string]any{"messages": messages, "cwd": directory, "sessionPath": filepath.Join(directory, "pi-session.jsonl")})
	if err != nil {
		t.Fatal(err)
	}
	command := exec.Command("node", filepath.Join("..", "pi", "session-fixture.mjs"))
	command.Stdin = bytes.NewReader(raw)
	snapshot, err := command.Output()
	if err != nil {
		t.Fatalf("seed native Pi session: %v", err)
	}
	return &agent.ContextCheckpoint{Version: agent.ContextCheckpointVersion, LastSequence: uint64(len(messages)), PiSession: snapshot}
}

func nativeTranscript(t *testing.T, checkpoint *agent.ContextCheckpoint) string {
	t.Helper()
	var reference struct {
		File   string `json:"file"`
		Offset int64  `json:"offset"`
	}
	if err := json.Unmarshal(checkpoint.PiSession, &reference); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(reference.File)
	if err != nil || reference.Offset > int64(len(raw)) {
		t.Fatalf("read Pi transcript: bytes=%d error=%v", len(raw), err)
	}
	return string(raw[:reference.Offset])
}

func TestPiOwnsSessionAndToolLifecycle(t *testing.T) {
	var requests, executions, saves int
	var events []string
	directory := t.TempDir()
	loop := &agent.Loop{SessionDir: t.TempDir(),
		Directory: directory,
		Tools: []agent.Tool{testTool("probe", func(context.Context, json.RawMessage) (string, error) {
			executions++
			return "evidence", nil
		})},
		Emit: func(event agent.Event) { events = append(events, event.Type) },
		SaveState: func(history []agent.Message, checkpoint *agent.ContextCheckpoint) error {
			saves++
			if len(checkpoint.PiSession) == 0 {
				t.Fatal("persisted state lacks the canonical Pi session")
			}
			if len(history) > 0 && history[len(history)-1].Sequence > checkpoint.LastSequence {
				t.Fatal("history sequence exceeds checkpoint")
			}
			return nil
		},
	}
	loop.Provider = providerFunc(func(_ context.Context, messages []agent.Message, _ []agent.Definition) (agent.Message, error) {
		requests++
		if requests == 1 {
			return toolCall("call-1", "probe"), nil
		}
		if !hasText(messages, "task") {
			t.Fatal("Pi lost the original task")
		}
		return agent.Text("assistant", "complete"), nil
	})
	result, err := loop.Run(context.Background(), "task")
	if err != nil || result != "complete" || requests != 2 || executions != 1 || saves < 4 {
		t.Fatalf("result=%q error=%v requests=%d executions=%d saves=%d", result, err, requests, executions, saves)
	}
	var snapshot struct {
		Header struct {
			Type    string `json:"type"`
			Version int    `json:"version"`
			Cwd     string `json:"cwd"`
		} `json:"header"`
		Entries json.RawMessage `json:"entries"`
	}
	if err := json.Unmarshal(loop.Checkpoint.PiSession, &snapshot); err != nil {
		t.Fatal(err)
	}
	if snapshot.Header.Type != "session" || snapshot.Header.Version != 3 || snapshot.Header.Cwd != directory {
		t.Fatalf("not a Pi SessionManager snapshot: %+v", snapshot.Header)
	}
	if len(snapshot.Entries) > 0 {
		t.Fatal("checkpoint duplicated native Pi transcript entries")
	}
	if !strings.Contains(nativeTranscript(t, loop.Checkpoint), `"role":"toolResult"`) {
		t.Fatal("Pi canonical toolResult message missing")
	}
	joined := strings.Join(events, ",")
	for _, event := range []string{"agent_start", "tool_start", "tool_end", "agent_end"} {
		if !strings.Contains(joined, event) {
			t.Fatalf("missing %s event: %s", event, joined)
		}
	}

	reservedSequence := loop.Checkpoint.LastSequence + 100
	loop.History = []agent.Message{agent.Text("user", "corrupt projection")}
	// The application journal can reserve IDs from a crash tail that is not in
	// the Pi snapshot; restoration must never reuse those evidence IDs.
	loop.Checkpoint.LastSequence = reservedSequence
	loop.Directory = "ignored-when-restoring-an-existing-session"
	loop.TaskPrompt = "corrupt task cache"
	if err := loop.Restore(context.Background()); err != nil {
		t.Fatal(err)
	}
	if hasText(loop.History, "corrupt projection") || !hasText(loop.History, "complete") {
		t.Fatal("restoration trusted the Go history cache over Pi")
	}
	if loop.TaskPrompt != "task" {
		t.Fatal("restoration did not recover the original Pi task")
	}
	if loop.Checkpoint.LastSequence != reservedSequence {
		t.Fatal("restoration discarded the execution journal sequence reservation")
	}
	if err := json.Unmarshal(loop.Checkpoint.PiSession, &snapshot); err != nil || snapshot.Header.Cwd != directory {
		t.Fatal("restoration changed the existing Pi session workspace")
	}
	checkpoint := loop.SnapshotCheckpoint()
	checkpoint.PiSession[0] = '!'
	if loop.Checkpoint.PiSession[0] != '{' {
		t.Fatal("snapshot leaked mutable canonical Pi storage")
	}
}

func TestPiHookInstructionIsDurableBeforeHookReturns(t *testing.T) {
	const instruction = "fresh phase instruction"
	var savedInstruction, hookFinished bool
	loop := &agent.Loop{SessionDir: t.TempDir()}
	loop.SaveState = func(history []agent.Message, checkpoint *agent.ContextCheckpoint) error {
		if hasText(history, instruction) {
			savedInstruction = true
			if len(checkpoint.PiSession) == 0 {
				t.Fatal("instruction lacks canonical session")
			}
		}
		return nil
	}
	loop.BeforeRequest = func(ctx context.Context, current *agent.Loop) (context.Context, error) {
		if !hookFinished {
			before := current.Checkpoint.LastSequence
			if err := current.AppendInstruction(instruction); err != nil {
				return nil, err
			}
			if !savedInstruction || current.Checkpoint.LastSequence <= before {
				t.Fatal("AppendInstruction returned before its durable Pi commit")
			}
			hookFinished = true
		}
		return ctx, nil
	}
	loop.Provider = providerFunc(func(_ context.Context, messages []agent.Message, _ []agent.Definition) (agent.Message, error) {
		if !hasText(messages, instruction) {
			t.Fatal("running Pi kernel did not adopt the hook's committed session")
		}
		return agent.Text("assistant", "done"), nil
	})
	if _, err := loop.Run(context.Background(), "task"); err != nil {
		t.Fatal(err)
	}
	if !hasText(loop.History, instruction) {
		t.Fatal("later Pi save discarded hook instruction")
	}
}

func TestPiPreservesModelErrorType(t *testing.T) {
	cause := errors.New("upstream unavailable")
	modelError := &agent.ModelError{Kind: agent.ErrorUnavailable, Err: cause}
	loop := &agent.Loop{SessionDir: t.TempDir(), Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
		return agent.Message{}, modelError
	})}
	_, err := loop.Run(context.Background(), "task")
	if !errors.Is(err, cause) {
		t.Fatalf("model error identity was lost through Pi: %v", err)
	}
	var typed *agent.ModelError
	if !errors.As(err, &typed) || typed.Kind != agent.ErrorUnavailable {
		t.Fatalf("wrong model error classification: %v", err)
	}
}

func TestPiUsesReplacementContextAndCancels(t *testing.T) {
	type phaseKey struct{}
	loop := &agent.Loop{SessionDir: t.TempDir()}
	var cancel context.CancelFunc
	defer func() {
		if cancel != nil {
			cancel()
		}
	}()
	loop.BeforeRequest = func(ctx context.Context, _ *agent.Loop) (context.Context, error) {
		next := context.WithValue(ctx, phaseKey{}, "conclusion")
		next, cancel = context.WithCancel(next)
		return next, nil
	}
	loop.Provider = providerFunc(func(ctx context.Context, _ []agent.Message, _ []agent.Definition) (agent.Message, error) {
		if ctx.Value(phaseKey{}) != "conclusion" {
			t.Fatal("provider used the stale phase context")
		}
		cancel()
		<-ctx.Done()
		return agent.Message{}, ctx.Err()
	})
	started := time.Now()
	_, err := loop.Run(context.Background(), "task")
	if !errors.Is(err, context.Canceled) || time.Since(started) > 5*time.Second {
		t.Fatalf("Pi cancellation failed or stalled: %v", err)
	}
}

func TestPiDoesNotExecuteBeforeAssistantSave(t *testing.T) {
	persistenceError := errors.New("disk write rejected")
	executed := false
	loop := &agent.Loop{SessionDir: t.TempDir(),
		Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
			return toolCall("call-1", "write"), nil
		}),
		Tools: []agent.Tool{testTool("write", func(context.Context, json.RawMessage) (string, error) {
			executed = true
			return "written", nil
		})},
		SaveState: func(history []agent.Message, _ *agent.ContextCheckpoint) error {
			if len(history) > 0 && history[len(history)-1].Role == "assistant" {
				return persistenceError
			}
			return nil
		},
	}
	_, err := loop.Run(context.Background(), "task")
	if !errors.Is(err, persistenceError) || executed {
		t.Fatalf("error=%v executed=%v; tool must wait for the assistant commit", err, executed)
	}
}

func TestPiMissingRuntimeHasNoNativeFallback(t *testing.T) {
	t.Setenv("PWNMESH_PI_RUNTIME", filepath.Join(t.TempDir(), "missing.mjs"))
	called := false
	loop := &agent.Loop{SessionDir: t.TempDir(), Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
		called = true
		return agent.Text("assistant", "native fallback"), nil
	})}
	if _, err := loop.Run(context.Background(), "task"); err == nil || called {
		t.Fatalf("missing Pi runtime should fail before provider execution: %v, called=%v", err, called)
	}
}

func TestPiRejectsUnsupportedCheckpointsAndHistoryWithoutCanonicalSession(t *testing.T) {
	for _, version := range []int{1, 3} {
		loop := &agent.Loop{SessionDir: t.TempDir(), Checkpoint: &agent.ContextCheckpoint{Version: version}}
		if err := loop.Restore(context.Background()); err == nil {
			t.Fatalf("restore accepted unsupported checkpoint version %d", version)
		}
		if err := loop.RepairHistory(); err == nil {
			t.Fatalf("repair accepted unsupported checkpoint version %d", version)
		}
		if err := loop.AppendInstruction("unsupported"); err == nil || !strings.Contains(err.Error(), "unsupported context checkpoint version") {
			t.Fatalf("edit accepted checkpoint version %d: %v", version, err)
		}
	}
	for _, checkpoint := range []*agent.ContextCheckpoint{nil, {Version: agent.ContextCheckpointVersion}} {
		loop := &agent.Loop{SessionDir: t.TempDir(), History: []agent.Message{agent.Text("user", "untrusted projection")}, Checkpoint: checkpoint}
		if err := loop.Restore(context.Background()); err == nil || !strings.Contains(err.Error(), "canonical Pi session") {
			t.Fatalf("projection restored without canonical state: %v", err)
		}
		if err := loop.AppendInstruction("new task"); err == nil {
			t.Fatal("edit silently imported a projection")
		}
	}
}

func TestPiRequiresFileSessionAndRejectsInlineCheckpoints(t *testing.T) {
	loop := &agent.Loop{}
	if err := loop.AppendInstruction("task"); err == nil || !strings.Contains(err.Error(), "session directory") {
		t.Fatalf("edit allowed a session without a transcript directory: %v", err)
	}
	loop.SessionDir = t.TempDir()
	loop.Checkpoint = &agent.ContextCheckpoint{Version: agent.ContextCheckpointVersion,
		PiSession: json.RawMessage(`{"header":{"type":"session","version":3,"id":"old-inline"},"entries":[]}`)}
	if err := loop.Restore(context.Background()); err == nil || !strings.Contains(err.Error(), "session file checkpoint") {
		t.Fatalf("restore allowed inline transcript migration: %v", err)
	}
}

func TestPiRepairsInterruptedCallsWithoutReplaying(t *testing.T) {
	directory := t.TempDir()
	loop := &agent.Loop{SessionDir: directory, Checkpoint: nativeCheckpoint(t, directory, agent.Text("user", "task"), toolCall("interrupted", "write"))}
	if err := loop.RepairHistory(); err != nil {
		t.Fatal(err)
	}
	if len(loop.History) != 3 || len(loop.Checkpoint.PiSession) == 0 {
		t.Fatalf("Pi did not settle the interrupted session: %+v", loop.History)
	}
	result := loop.History[2].Content[0]
	if result.Type != "tool_result" || result.ToolUseID != "interrupted" || !result.IsError {
		t.Fatalf("wrong recovery receipt: %+v", result)
	}
	sequence := loop.Checkpoint.LastSequence
	if err := loop.RepairHistory(); err != nil {
		t.Fatal(err)
	}
	if sequence != loop.Checkpoint.LastSequence {
		t.Fatal("repair replayed an already settled receipt")
	}
}

func TestPiRepairsReusedToolIDAtLatestBoundary(t *testing.T) {
	directory := t.TempDir()
	loop := &agent.Loop{SessionDir: directory, Checkpoint: nativeCheckpoint(t, directory,
		agent.Text("user", "task"),
		toolCall("reused", "write"),
		agent.Message{Role: "user", Content: []agent.Block{{Type: "tool_result", ToolUseID: "reused", Content: json.RawMessage(`"first result"`)}}},
		toolCall("reused", "write"),
	)}
	if err := loop.RepairHistory(); err != nil {
		t.Fatal(err)
	}
	if len(loop.History) != 5 || !loop.History[4].Content[0].IsError {
		t.Fatal("an earlier receipt incorrectly settled the latest interrupted call with the same ID")
	}
}

func TestPiTruncatedCallsNeverExecute(t *testing.T) {
	requests, executions := 0, 0
	loop := &agent.Loop{SessionDir: t.TempDir(),
		Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
			requests++
			if requests == 1 {
				message := toolCall("truncated", "write")
				message.StopReason = "max_tokens"
				message.Content[0].Input = json.RawMessage(`{"broken":`)
				return message, nil
			}
			return agent.Text("assistant", "done"), nil
		}),
		Tools: []agent.Tool{testTool("write", func(context.Context, json.RawMessage) (string, error) {
			executions++
			return "written", nil
		})},
	}
	if _, err := loop.Run(context.Background(), "task"); err != nil {
		t.Fatal(err)
	}
	if executions != 0 {
		t.Fatal("Pi executed a truncated tool call")
	}
}

func TestPiByteBudgetIncludesToolDefinitions(t *testing.T) {
	calls := 0
	tool := testTool("large_schema", func(context.Context, json.RawMessage) (string, error) {
		t.Fatal("oversized tool must never execute")
		return "", nil
	})
	tool.Description = strings.Repeat("Large tool documentation. ", 1000)
	loop := &agent.Loop{SessionDir: t.TempDir(),
		ContextBytes: 2000,
		Tools:        []agent.Tool{tool},
		Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
			calls++
			return agent.Text("assistant", "summary"), nil
		}),
	}
	_, err := loop.Run(context.Background(), "short task")
	var modelError *agent.ModelError
	if !errors.As(err, &modelError) || modelError.Kind != agent.ErrorBudget {
		t.Fatalf("oversized declarations bypassed input budget: %v", err)
	}
	if calls > 1 {
		t.Fatalf("budget failure performed repeated provider calls: %d", calls)
	}
}

func TestPiKeepsFailedToolEvidenceAndStopsAfterCommit(t *testing.T) {
	requests, commits, laterCalls := 0, 0, 0
	loop := &agent.Loop{SessionDir: t.TempDir(),
		Provider: providerFunc(func(_ context.Context, messages []agent.Message, _ []agent.Definition) (agent.Message, error) {
			requests++
			if requests == 1 {
				return toolCall("failure", "probe"), nil
			}
			var failedEvidence string
			for _, message := range messages {
				for _, block := range message.Content {
					if block.Type == "tool_result" && block.ToolUseID == "failure" {
						if err := json.Unmarshal(block.Content, &failedEvidence); err != nil {
							t.Fatal(err)
						}
					}
				}
			}
			if !strings.Contains(failedEvidence, "partial evidence") || !strings.Contains(failedEvidence, "probe failed") {
				t.Fatalf("failed tool lost its diagnostics: %q", failedEvidence)
			}
			message := toolCall("commit", "finish")
			message.Content = append(message.Content, toolCall("later", "write").Content...)
			return message, nil
		}),
		Tools: []agent.Tool{
			testTool("probe", func(context.Context, json.RawMessage) (string, error) {
				return "partial evidence", errors.New("probe failed")
			}),
			testTool("finish", func(context.Context, json.RawMessage) (string, error) {
				commits++
				return "committed", nil
			}),
			testTool("write", func(context.Context, json.RawMessage) (string, error) {
				laterCalls++
				return "changed", nil
			}),
		},
		StopResult: func() (string, bool) { return "terminal receipt", commits > 0 },
	}
	result, err := loop.Run(context.Background(), "task")
	if err != nil || result != "terminal receipt" || commits != 1 || laterCalls != 0 || requests != 2 {
		t.Fatalf("result=%q error=%v commits=%d later=%d requests=%d", result, err, commits, laterCalls, requests)
	}
}

func TestPiFileCheckpointRetainsLargeHistoryAndIgnoresLaterTail(t *testing.T) {
	dir := t.TempDir()
	compacted := false
	loop := &agent.Loop{
		Directory: dir, SessionDir: dir, TaskPrompt: "current task",
		Emit:         func(event agent.Event) { compacted = compacted || event.Type == "context_compacted" },
		ContextBytes: 2 << 20, ContextTokens: 1000, ContextTargetTokens: 500,
		Checkpoint: nativeCheckpoint(t, dir,
			agent.Text("user", strings.Repeat("historical evidence ", 60000)),
			agent.Text("assistant", "old response"),
			agent.Text("user", strings.Repeat("recent evidence one ", 60)),
			agent.Text("assistant", "recent response one"),
			agent.Text("user", strings.Repeat("recent evidence two ", 60)),
			agent.Text("assistant", "recent response two"),
			agent.Text("user", strings.Repeat("recent evidence three ", 60)),
			agent.Text("assistant", "recent response three"),
			agent.Text("user", strings.Repeat("recent evidence four ", 60)),
			agent.Text("assistant", "recent response four"),
		),
		Provider: providerFunc(func(context.Context, []agent.Message, []agent.Definition) (agent.Message, error) {
			return agent.Text("assistant", "concise retained account"), nil
		}),
	}
	if _, err := loop.Run(context.Background(), "continue"); err != nil {
		t.Fatal(err)
	}
	if !compacted || len(loop.Checkpoint.PiSession) > 4096 {
		t.Fatalf("canonical transcript leaked into bounded checkpoint: compacted=%v bytes=%d",
			compacted, len(loop.Checkpoint.PiSession))
	}
	var reference struct {
		File   string `json:"file"`
		Offset int64  `json:"offset"`
	}
	if err := json.Unmarshal(loop.Checkpoint.PiSession, &reference); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(reference.File)
	if err != nil || info.Size() < 1<<20 || info.Size() != reference.Offset {
		t.Fatalf("Pi did not retain its complete JSONL transcript: info=%v error=%v", info, err)
	}
	committed := loop.SnapshotCheckpoint()
	if err := loop.AppendInstruction("later uncommitted branch"); err != nil {
		t.Fatal(err)
	}
	restored := &agent.Loop{Directory: dir, SessionDir: dir, Checkpoint: committed}
	if err := restored.Restore(context.Background()); err != nil {
		t.Fatal(err)
	}
	if hasText(restored.History, "later uncommitted branch") || !hasText(restored.History, "concise retained account") {
		t.Fatal("restoration used the file tail instead of its committed Pi leaf")
	}
	if err := restored.AppendInstruction("replacement branch"); err != nil {
		t.Fatal(err)
	}
	if hasText(restored.History, "later uncommitted branch") || !hasText(restored.History, "replacement branch") {
		t.Fatal("new instruction resumed an uncommitted Pi branch")
	}
}
