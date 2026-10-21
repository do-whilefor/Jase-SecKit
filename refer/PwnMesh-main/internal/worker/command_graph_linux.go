//go:build linux

package worker

import (
	"context"
	"encoding/json"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/worker/dag"
	"pwnmesh/internal/workergraph"
)

// Each call runs the currently known graph. The parent Loop can observe its
// results and append tasks on a later call; every child owns a separate Loop.
func commandGraphTool(j Job, o Options) agent.Tool {
	tool := agent.Tool{Definition: agent.Definition{
		Name:        "run_graph",
		Description: commandGraphDescription,
		Schema:      json.RawMessage(commandGraphInputSchema),
	}, Execute: agent.TextExecutor(func(ctx context.Context, raw json.RawMessage) (string, error) {
		return runCommandGraph(ctx, j, o, raw)
	})}
	return tool
}

const commandGraphInputSchema = `{
  "type":"object",
  "properties":{
    "key":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
    "append":{"type":"boolean","description":"Send additions only; returns bounded changes and checkpoint_path for the complete graph."},
    "parallelism":{"type":"integer","minimum":1,"maximum":16},
    "nodes":{
      "type":"array","minItems":1,"maxItems":64,
      "items":{
        "type":"object",
        "properties":{
          "id":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
          "kind":{"type":"string","enum":["command","agent","reuse"],"description":"command (default) requires command; agent requires task; reuse requires reuse_from."},
          "command":{"type":"string","minLength":1,"maxLength":32768},
          "task":{"type":"string","minLength":1,"maxLength":32768},
          "timeout":{"type":"integer","minimum":1,"maximum":600},
          "depends_on":{
            "type":"array","maxItems":64,
            "items":{
              "type":"object",
              "properties":{"id":{"type":"string"},"optional":{"type":"boolean"}},
              "required":["id"],"additionalProperties":false
            }
          },
          "resources":{"type":"array","maxItems":16,"items":{"type":"string","minLength":1,"maxLength":128}},
          "artifacts":{"type":"array","maxItems":16,"items":{"type":"string","minLength":1,"maxLength":256},"description":"Declared output files relative to PWNMESH_NODE_DIR; [] means logs only."},
          "optional":{"type":"boolean"},
          "when":{
            "type":"object",
            "properties":{
              "node":{"type":"string"},
              "status":{"type":"string","enum":["succeeded","failed","skipped"]},
              "contains":{"type":"string","minLength":1,"maxLength":256}
            },
            "required":["node"],"additionalProperties":false
          },
          "inputs":{
            "type":"array","maxItems":64,
            "items":{
              "type":"object",
              "properties":{"node":{"type":"string"},"artifact":{"type":"string"}},
              "required":["node","artifact"],"additionalProperties":false
            },
            "description":"Required named files from direct required dependencies; validated before graph execution and before consumption."
          },
          "reuse_from":{
            "type":"object",
            "description":"With kind:reuse, select a node from a different graph key. Set resources:[] and inputs:[]; omit command, task, timeout, depends_on, artifacts and when. Source definitions cannot be overridden.",
            "properties":{
              "key":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
              "node":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"}
            },
            "required":["key","node"],"additionalProperties":false
          }
        },
        "required":["id","resources","inputs"],"additionalProperties":false
      }
    }
  },
  "required":["key","nodes"],"additionalProperties":false
}`

func commandGraphScope(j Job, runDir string) dag.Scope {
	scope := dag.Scope{RunID: j.RunID, RunDir: runDir, Workspace: j.Workspace, SharedWritesBound: j.Intent != nil, Identity: func(dir string) (json.RawMessage, error) {
		identity, err := identityFor(j, dir)
		if err != nil {
			return nil, err
		}
		return json.Marshal(identity)
	}}
	// Read only the originally bound Step, never current shared graph state.
	if j.Intent != nil {
		var input struct {
			Steps []struct {
				ID         string   `json:"id"`
				WritePaths []string `json:"write_paths"`
			} `json:"steps"`
		}
		if json.Unmarshal(j.InputView, &input) == nil {
			for _, step := range input.Steps {
				if step.ID == j.Intent.ID {
					scope.WritePaths = append(scope.WritePaths, step.WritePaths...)
				}
			}
		}
		if j.Repair != nil {
			scope.WritePaths = append(scope.WritePaths, j.Repair.Path)
		}
	}
	return scope
}

func runCommandGraph(ctx context.Context, j Job, o Options, raw json.RawMessage) (string, error) {
	if !o.graphDeadline.IsZero() {
		var cancel context.CancelFunc
		ctx, cancel = context.WithDeadline(ctx, o.graphDeadline)
		defer cancel()
	}
	return dag.Run(ctx, commandGraphScope(j, o.RunDir), raw, &dag.AgentExecutor{
		Run: func(ctx context.Context, node dag.AgentNode) (workergraph.Output, error) {
			return executeAgentNode(ctx, j, o, node)
		},
		Reconcile: func(ctx context.Context, node dag.AgentNode) (workergraph.Output, error) {
			return reconcileAgentNode(ctx, j, node)
		},
	})
}
