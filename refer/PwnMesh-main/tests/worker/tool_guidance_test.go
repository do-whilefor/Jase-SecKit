//go:build linux

package worker_test

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelwire"
	"pwnmesh/internal/worker"
)

type guidanceProvider func([]agent.Message, []agent.Definition) (agent.Message, error)

func (p guidanceProvider) Generate(_ context.Context, history []agent.Message, tools []agent.Definition, _ agent.Emit) (agent.Message, error) {
	return p(history, tools)
}

func (p guidanceProvider) GenerateSummary(_ context.Context, history []agent.Message, _ int, _ agent.Emit) (agent.Message, error) {
	return p(history, nil)
}

func (p guidanceProvider) InputBytes(history []agent.Message, tools []agent.Definition) (int, error) {
	return (modelwire.RequestFormat{}).InputBytes(history, tools)
}

func TestToolGuidanceFollowsCapabilitiesAndPhase(t *testing.T) {
	for _, phase := range []string{"repair", "conclude"} {
		t.Run(phase, func(t *testing.T) {
			workspace := t.TempDir()
			runDir := filepath.Join(workspace, ".pwnmesh", "runs", "run")
			job := snapshotJob(workspace)
			available := []agent.Tool{
				{Definition: agent.Definition{Name: "lookup", Schema: json.RawMessage(`{"type":"object"}`)}, PromptGuidelines: []string{"  Keep lookup results scoped.  ", "", "Preserve uncertainty."}},
				{Definition: agent.Definition{Name: "inspect", Schema: json.RawMessage(`{"type":"object"}`)}, PromptGuidelines: []string{"Keep lookup results scoped.", "Inspect only supplied records."}},
			}
			softStop := make(chan struct{})
			calls := 0
			provider := guidanceProvider(func(history []agent.Message, definitions []agent.Definition) (agent.Message, error) {
				calls++
				var guidance, request string
				blocks := 0
				for _, message := range history {
					if message.Role != "user" {
						continue
					}
					text := message.Text()
					request += text + "\n"
					if strings.HasPrefix(text, "Guidance for currently available tools:\n") {
						guidance = text
						blocks++
					}
				}
				if !strings.Contains(request, "Automatic dependency review failed") {
					t.Error("capability projection removed the unrelated graph update notice")
				}
				if !strings.Contains(request, "Probes, retries and child tasks share the task's operation limits") || !strings.Contains(request, "When returning JSON, return one JSON object") {
					t.Error("capability projection lost the task's execution or result contract")
				}
				if calls == 1 {
					want := "Guidance for currently available tools:\n- Keep lookup results scoped.\n- Preserve uncertainty.\n- Inspect only supplied records."
					if blocks != 1 || guidance != want {
						t.Errorf("active guidelines are not deduplicated in capability order: %q", guidance)
					}
					if strings.Contains(request, "Run complete commands") || strings.Contains(request, "source_path") {
						t.Error("unavailable shell or file tools contributed guidance")
					}
					for _, tool := range definitions {
						if tool.Name == "bash" || tool.Name == "write" {
							t.Errorf("custom capability subset acquired %q", tool.Name)
						}
					}
					if phase == "conclude" {
						close(softStop)
					} else {
						message := agent.Text("assistant", "invalid result")
						message.StopReason = "end_turn"
						return message, nil
					}
				} else if blocks != 0 || len(definitions) != 0 || !strings.Contains(request, "All tools are disabled") {
					t.Errorf("disabled phase kept active guidance or tools: blocks=%d tools=%d", blocks, len(definitions))
				}
				message := agent.Text("assistant", `{"accepted":true,"outcome":"incomplete","reason":"No target observations were collected."}`)
				message.StopReason = "end_turn"
				return message, nil
			})
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			result, err := worker.Run(ctx, job, worker.Options{
				Provider: provider, Tools: available, RunDir: runDir,
				Output: &recoveryOutput{runDir: runDir}, SoftStop: softStop,
			})
			if err != nil || result.Status != "failed" || result.FailureKind != "incomplete" || calls != 2 || result.Conclude != (phase == "conclude") {
				t.Fatalf("phase transition failed: result=%+v err=%v calls=%d", result, err, calls)
			}
			raw, err := os.ReadFile(filepath.Join(runDir, "session.json"))
			if err != nil {
				t.Fatal(err)
			}
			var saved map[string]json.RawMessage
			if err := json.Unmarshal(raw, &saved); err != nil {
				t.Fatal(err)
			}
			if _, exists := saved["task_prompt"]; exists {
				t.Error("worker persisted a duplicate task prompt")
			}
		})
	}
}
