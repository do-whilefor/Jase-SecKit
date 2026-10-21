//go:build linux

package worker_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"pwnmesh/internal/agent"
	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/modelrpc"
	"pwnmesh/internal/modelwire"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/worker"
)

type recoveryProvider func([]agent.Message) (agent.Message, error)

func (p recoveryProvider) Generate(_ context.Context, history []agent.Message, _ []agent.Definition, _ agent.Emit) (agent.Message, error) {
	return p(history)
}

func (p recoveryProvider) GenerateSummary(_ context.Context, history []agent.Message, _ int, _ agent.Emit) (agent.Message, error) {
	return p(history)
}

func (p recoveryProvider) InputBytes(history []agent.Message, tools []agent.Definition) (int, error) {
	return (modelwire.RequestFormat{}).InputBytes(history, tools)
}

// Keep the real Worker graph bridge local and immediate. A read failure follows
// the existing bounded notice path without a server or target connection.
type recoveryOutput struct {
	runDir  string
	pending []byte
	model   func(modelrpc.Request) modelrpc.Response
	graph   func(protocol.GraphRequest) protocol.GraphResponse
}

func (w *recoveryOutput) Write(p []byte) (int, error) {
	w.pending = append(w.pending, p...)
	for {
		n := bytes.IndexByte(w.pending, '\n')
		if n < 0 {
			return len(p), nil
		}
		frame := w.pending[:n]
		var event protocol.GraphRequestEvent
		if err := json.Unmarshal(frame, &event); err != nil {
			return 0, err
		}
		w.pending = w.pending[n+1:]
		if event.Type == "model_request" && w.model != nil {
			var request modelrpc.RequestEvent
			if err := json.Unmarshal(frame, &request); err != nil {
				return 0, err
			}
			response := w.model(request.Request)
			response.RequestID = request.Request.RequestID
			raw, err := json.Marshal(response)
			if err != nil {
				return 0, err
			}
			path := filepath.Join(w.runDir, "model-response-"+response.RequestID+".json")
			if err := os.WriteFile(path, raw, 0600); err != nil {
				return 0, err
			}
			continue
		}
		if event.Type != "graph_request" {
			continue
		}
		reply := protocol.GraphResponse{
			RequestID: event.Request.RequestID,
			Failure:   &protocol.RPCError{Code: protocol.CodeRequestFailed, Detail: "test graph unavailable"},
		}
		if w.graph != nil {
			reply = w.graph(event.Request)
			reply.RequestID = event.Request.RequestID
		} else if event.Request.Op != "read_updates" {
			return 0, errors.New("unexpected graph request in recovery test")
		}
		response, err := json.Marshal(reply)
		if err != nil {
			return 0, err
		}
		name := filepath.Join(w.runDir, "graph-response-"+event.Request.RequestID+".json")
		if err := os.WriteFile(name, response, 0600); err != nil {
			return 0, err
		}
	}
}

func recoveryNotices(history []agent.Message) []string {
	var notices []string
	for _, message := range history {
		if message.Role != "user" {
			continue
		}
		text := message.Text()
		if strings.HasPrefix(text, "Retained work index (") {
			notices = append(notices, text)
		}
	}
	return notices
}

func TestSetupOnlyDecisionRecoveryKeepsOriginalTaskFirst(t *testing.T) {
	job := snapshotJob(t.TempDir())
	job.Kind, job.Intent = "reason", nil
	job.Decision = &board.DecisionContext{Version: 2, StateVersion: job.InputSnapshot.StateVersion,
		Generation: job.InputSnapshot.Generation, ToRevision: job.InputSnapshot.Revision, View: job.InputView}
	job.InputView = nil
	runDir := filepath.Join(job.Workspace, "run")
	writeBoundSession(t, job, runDir, nil)
	t.Setenv("PWNMESH_WORKER_ENVIRONMENT", "kali-headless")
	assignment, err := worker.Prompt(job, false)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	output := &recoveryOutput{runDir: runDir, graph: func(request protocol.GraphRequest) protocol.GraphResponse {
		if request.Op != "decision_receipt" {
			t.Errorf("unexpected graph request: %s", request.Op)
		}
		raw, _ := json.Marshal(board.DecisionReceipt{StateVersion: job.Decision.StateVersion})
		return protocol.GraphResponse{Result: raw}
	}}
	for attempt := 0; attempt < 2; attempt++ {
		calls := 0
		provider := recoveryProvider(func(history []agent.Message) (agent.Message, error) {
			calls++
			found := false
			for _, message := range history {
				found = found || message.Role == "user" && message.Text() == assignment
				if attempt == 0 && message.Role == "user" && strings.HasPrefix(message.Text(), "# Decision recovery") {
					t.Error("setup-only recovery inserted a notice before any task or draft existed")
				}
			}
			if !found {
				t.Error("recovery lost the original assignment")
			}
			return agent.Message{}, &agent.ModelError{Kind: agent.ErrorTransport, Err: errors.New("test upstream reset")}
		})
		result, err := worker.Run(ctx, job, worker.Options{RunDir: runDir, Provider: provider, Output: output})
		if err != nil || calls != 1 || result.Status != "failed" || result.Retryable != (attempt == 0) {
			t.Fatalf("attempt %d: calls=%d result=%+v error=%v", attempt, calls, result, err)
		}
		raw, err := os.ReadFile(filepath.Join(runDir, "session.json"))
		if err != nil {
			t.Fatal(err)
		}
		var saved struct {
			Checkpoint *agent.ContextCheckpoint `json:"context_checkpoint"`
		}
		if err := json.Unmarshal(raw, &saved); err != nil {
			t.Fatal(err)
		}
		restored := &agent.Loop{Directory: job.Workspace, SessionDir: runDir, Checkpoint: saved.Checkpoint}
		if err := restored.Restore(ctx); err != nil {
			t.Fatal(err)
		}
		if restored.TaskPrompt != assignment {
			t.Errorf("attempt %d restored a recovery notice instead of the original task", attempt)
		}
		t.Setenv("PWNMESH_WORKER_ENVIRONMENT", "")
	}
}

func TestRecoveryRetainsOneCopyOfUnchangedWorkIndex(t *testing.T) {
	for _, changed := range []bool{false, true} {
		name := "unchanged"
		if changed {
			name = "changed"
		}
		t.Run(name, func(t *testing.T) {
			workspace := t.TempDir()
			runDir := filepath.Join(workspace, ".pwnmesh", "runs", "run")
			job := snapshotJob(workspace)
			// Three attempts start several real Pi processes. Bound hangs without
			// making recovery correctness depend on parallel test/build load.
			ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
			defer cancel()
			var firstNotice, assignment string
			for attempt := 0; attempt < 3; attempt++ {
				if attempt == 0 {
					t.Setenv("PWNMESH_WORKER_ENVIRONMENT", "kali-headless")
				} else {
					t.Setenv("PWNMESH_WORKER_ENVIRONMENT", "")
				}
				var notices []string
				calls := 0
				provider := recoveryProvider(func(history []agent.Message) (agent.Message, error) {
					calls++
					if calls == 1 {
						originalAssignment := false
						for _, message := range history {
							if message.Role == "user" && strings.Contains(message.Text(), "# Current assignment") {
								if assignment == "" {
									assignment = message.Text()
								}
								originalAssignment = originalAssignment || message.Text() == assignment
								if message.Text() != assignment {
									t.Error("recovery rebuilt the assignment from the changed environment")
								}
							}
						}
						if !originalAssignment {
							t.Error("request lost the original Pi assignment")
						}
						if attempt == 0 {
							guidance := false
							for _, message := range history {
								guidance = guidance || message.Role == "user" && strings.Contains(message.Text(), "source_path")
							}
							if !guidance {
								t.Error("initial request lacks script reuse guidance")
							}
						}
						notices = recoveryNotices(history)
						var tool string
						var arguments any
						if attempt == 0 {
							tool = "write"
							arguments = map[string]string{"path": "script.sh", "content": "printf first\n"}
						} else if attempt == 1 && changed {
							tool = "edit"
							arguments = map[string]any{"path": "script.sh", "edits": []map[string]string{{"oldText": "first", "newText": "second"}}}
						}
						if tool != "" {
							raw, _ := json.Marshal(arguments)
							return agent.Message{Role: "assistant", StopReason: "tool_use", Content: []agent.Block{
								{Type: "tool_use", ID: tool, Name: tool, Input: raw},
							}}, nil
						}
					}
					return agent.Message{}, &agent.ModelError{Kind: agent.ErrorTransport, Err: errors.New("test upstream reset")}
				})
				result, err := worker.Run(ctx, job, worker.Options{
					Provider: provider, RunDir: runDir, Output: &recoveryOutput{runDir: runDir},
				})
				if err != nil || calls == 0 {
					t.Fatalf("attempt %d did not reach the provider: result=%+v err=%v", attempt, result, err)
				}
				if result.Status != "failed" || result.Retryable != (attempt < 2) {
					t.Fatalf("attempt %d lost recovery semantics: %+v", attempt, result)
				}
				// Recovery depends on canonical Pi state without a Go history cache.
				path := filepath.Join(runDir, "session.json")
				raw, readErr := os.ReadFile(path)
				if readErr != nil {
					t.Fatal(readErr)
				}
				var saved map[string]json.RawMessage
				if err := json.Unmarshal(raw, &saved); err != nil {
					t.Fatal(err)
				}
				if string(saved["schema_version"]) != "4" {
					t.Fatal("Pi execution state is not fenced against older Go kernels")
				}
				if _, exists := saved["history"]; exists {
					t.Fatal("worker retained a duplicate history projection")
				}
				if _, exists := saved["task_prompt"]; exists {
					t.Fatal("worker retained a duplicate task prompt")
				}
				var checkpoint struct {
					CompactionCount json.RawMessage `json:"compaction_count"`
					PiSession       struct {
						Header struct {
							Type    string `json:"type"`
							Version int    `json:"version"`
						} `json:"header"`
						File   string `json:"file"`
						Offset int64  `json:"offset"`
						SHA256 string `json:"sha256"`
					} `json:"pi_session"`
				}
				if err := json.Unmarshal(saved["context_checkpoint"], &checkpoint); err != nil {
					t.Fatal(err)
				}
				if checkpoint.CompactionCount != nil {
					t.Fatal("worker retained a duplicate Pi compaction counter")
				}
				pi := checkpoint.PiSession
				if pi.Header.Type != "session" || pi.Header.Version != 3 || pi.File != filepath.Join(runDir, "pi-session.jsonl") || pi.Offset <= 0 || len(pi.SHA256) != 64 {
					t.Fatal("worker did not persist a canonical Pi SessionManager checkpoint")
				}
				if info, err := os.Stat(pi.File); err != nil || info.Size() < pi.Offset {
					t.Fatal("Pi checkpoint has no durable native transcript")
				}
				want := 0
				if attempt > 0 {
					want = 1
				}
				if len(notices) != want {
					t.Fatalf("attempt %d has %d retained-work notices, want %d", attempt, len(notices), want)
				}
				if attempt == 1 {
					firstNotice = notices[0]
				}
				// Pi projects the current pinned work index while keeping earlier
				// versions in its canonical transcript, outside the request view.
				if attempt == 2 && ((changed && notices[0] == firstNotice) || (!changed && notices[0] != firstNotice)) {
					t.Fatal("recovery failed to retain or refresh the current work index")
				}
			}
			want := "printf first\n"
			if changed {
				want = "printf second\n"
			}
			contents, err := os.ReadFile(filepath.Join(workspace, "script.sh"))
			if err != nil || string(contents) != want {
				t.Fatalf("retained script changed unexpectedly: contents=%q err=%v", contents, err)
			}
		})
	}
}
