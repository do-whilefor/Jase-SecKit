//go:build linux

package worker_test

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelrpc"
	"pwnmesh/internal/worker"
	"pwnmesh/internal/workergraph"
)

func TestGraphChildUsesPiSessionAndExistingModelBridge(t *testing.T) {
	workspace := t.TempDir()
	runDir := filepath.Join(workspace, ".pwnmesh", "runs", "run")
	if err := os.MkdirAll(runDir, 0700); err != nil {
		t.Fatal(err)
	}
	settings, err := json.Marshal(modelrpc.Settings{
		Protocol: "anthropic", Model: "test-model", MaxTokens: 4096,
		ReasoningEffort: "high", Timeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(runDir, "model-settings.json"), settings, 0600); err != nil {
		t.Fatal(err)
	}
	job := snapshotJob(workspace)
	calls, childCalls := 0, 0
	corruptChild := false
	output := &recoveryOutput{runDir: runDir, model: func(request modelrpc.Request) modelrpc.Response {
		childCalls++
		if request.SessionID != "run:kernel:child" {
			t.Errorf("child request escaped the parent launch: %q", request.SessionID)
		}
		for _, tool := range request.Tools {
			if tool.Name == "run_graph" || tool.Name == "finish_step" {
				t.Errorf("child acquired parent authority: %q", tool.Name)
			}
		}
		guidance := false
		for _, message := range request.Messages {
			guidance = guidance || message.Role == "user" && strings.HasPrefix(message.Text(), "Guidance for currently available tools:\n") && strings.Contains(message.Text(), "source_path")
		}
		if !guidance {
			t.Error("child request lacks its selected tool guidance")
		}
		message := agent.Text("assistant", "Child completed its local inspection.")
		message.StopReason = "end_turn"
		return modelrpc.Response{Message: message}
	}}
	provider := recoveryProvider(func(history []agent.Message) (agent.Message, error) {
		calls++
		if calls%2 == 1 {
			return agent.Message{Role: "assistant", StopReason: "tool_use", Content: []agent.Block{
				{Type: "tool_use", ID: "child-call", Name: "run_graph", Input: json.RawMessage(
					`{"key":"kernel","nodes":[{"id":"child","kind":"agent","task":"Return a short local account.","resources":[],"inputs":[],"timeout":15}]}`)},
			}}, nil
		}
		last := history[len(history)-1]
		if len(last.Content) == 0 || last.Content[0].Type != "tool_result" || last.Content[0].IsError != corruptChild {
			t.Errorf("unexpected child execution or recovery result: %+v", last)
		}
		return agent.Message{}, &agent.ModelError{Kind: agent.ErrorTransport, Err: errors.New("test stop")}
	})
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	result, err := worker.Run(ctx, job, worker.Options{Provider: provider, RunDir: runDir, Output: output})
	if err != nil || !result.Retryable || childCalls != 1 || calls != 2 {
		t.Fatalf("parent/child bridge: result=%+v error=%v calls=%d child=%d", result, err, calls, childCalls)
	}
	raw, err := os.ReadFile(filepath.Join(runDir, "graph-tools", "kernel", "nodes", "child", "session.json"))
	if err != nil {
		t.Fatal(err)
	}
	var child struct {
		SchemaVersion    int             `json:"schema_version"`
		History          json.RawMessage `json:"history"`
		InputHash        json.RawMessage `json:"input_sha256"`
		GraphInputSHA256 string          `json:"graph_input_sha256"`
		Checkpoint       struct {
			PiSession json.RawMessage `json:"pi_session"`
		} `json:"context_checkpoint"`
		Result string `json:"result"`
		Error  string `json:"error"`
	}
	if err = json.Unmarshal(raw, &child); err != nil {
		t.Fatal(err)
	}
	if child.Error != "" || child.Result == "" || !strings.Contains(string(child.Checkpoint.PiSession), `"type":"session"`) {
		t.Fatalf("child has no successful Pi session: %s", raw)
	}
	if child.SchemaVersion != 4 || child.History != nil || child.InputHash != nil {
		t.Fatal("child retained retired Go conversation metadata")
	}
	if len(child.GraphInputSHA256) != 64 {
		t.Fatal("child lost its graph input identity")
	}
	graphDir := filepath.Join(runDir, "graph-tools", "kernel")
	for attempt := 1; attempt <= 2; attempt++ {
		// Recreate the crash boundary after the child's terminal save but before
		// the graph accepted it. Recovery must inspect Pi without another model call.
		checkpoint, err := workergraph.ReadCheckpoint(ctx, graphDir)
		if err != nil {
			t.Fatal(err)
		}
		checkpoint.Status = "running"
		checkpoint.Nodes[0].Status = "running"
		checkpoint.Nodes[0].FinishedAt = time.Time{}
		checkpoint.Nodes[0].Output = workergraph.Output{}
		raw, err := json.Marshal(checkpoint)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(graphDir, "graph.json"), raw, 0600); err != nil {
			t.Fatal(err)
		}
		corruptChild = attempt == 2
		if corruptChild {
			if err := os.WriteFile(filepath.Join(graphDir, "nodes", "child", "pi-session.jsonl"), []byte("damaged\n"), 0600); err != nil {
				t.Fatal(err)
			}
		}
		result, err := worker.Run(ctx, job, worker.Options{Provider: provider, RunDir: runDir, Output: output})
		if err != nil || result.Retryable != (attempt < 2) || childCalls != 1 || calls != 2*(attempt+1) {
			t.Fatalf("child recovery replayed or lost its Pi receipt: result=%+v error=%v calls=%d child=%d", result, err, calls, childCalls)
		}
	}
}
