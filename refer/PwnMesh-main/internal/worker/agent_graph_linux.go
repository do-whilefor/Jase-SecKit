//go:build linux

package worker

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/tools"
	"pwnmesh/internal/worker/dag"
	eventlog "pwnmesh/internal/worker/internal/journal"
	"pwnmesh/internal/workergraph"
)

// A child session is local to an authorized parent Run. It has no lease,
// shared-graph tools, completion tool or recursive graph tool. Its checkpoint records the
// Pi session snapshot; uncertain side effects are never automatically replayed.
type graphAgentSession struct {
	SchemaVersion    int                      `json:"schema_version"`
	RunID            string                   `json:"run_id"`
	GraphKey         string                   `json:"graph_key"`
	NodeID           string                   `json:"node_id"`
	GraphInputSHA256 string                   `json:"graph_input_sha256,omitempty"`
	Deadline         time.Time                `json:"deadline"`
	Checkpoint       *agent.ContextCheckpoint `json:"context_checkpoint,omitempty"`
	ToolProgress     toolProgress             `json:"tool_progress,omitempty"`
	Log              eventlog.Checkpoint      `json:"log_checkpoint"`
	Result           string                   `json:"result,omitempty"`
	Error            string                   `json:"error,omitempty"`
	TerminalOutput   *workergraph.Output      `json:"terminal_output,omitempty"`
}

func executeAgentNode(ctx context.Context, j Job, o Options, node dag.AgentNode) (workergraph.Output, error) {
	key, dir, spec := node.Key, node.Dir, node.Spec
	parent := ctx
	ctx, cancel := context.WithTimeout(ctx, time.Duration(spec.Timeout)*time.Second)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return workergraph.Output{}, err
	}
	constraints, err := agentAssignmentContext(j)
	if err != nil {
		return workergraph.Output{}, err
	}
	views, err := node.PrepareInputs(ctx)
	if err != nil {
		return workergraph.Output{}, err
	}
	prompt, err := agentNodePrompt(j, dir, spec, constraints, views)
	if err != nil {
		return workergraph.Output{}, err
	}
	provider, err := modelForJob(j, o, j.RunID+":"+key+":"+spec.ID)
	if err != nil {
		return workergraph.Output{}, err
	}
	journal, err := eventlog.Open(dir, nil, nil)
	if err != nil {
		return workergraph.Output{}, err
	}
	defer journal.Close()
	deadline, _ := ctx.Deadline()
	state := graphAgentSession{SchemaVersion: sessionSchemaVersion, RunID: j.RunID, GraphKey: key, NodeID: spec.ID, GraphInputSHA256: node.InputSHA256, Deadline: deadline}
	var logErr error
	save := func(history []agent.Message, checkpoint *agent.ContextCheckpoint) error {
		if logErr != nil {
			return logErr
		}
		committed, err := journal.SyncCheckpoint()
		if err != nil {
			return err
		}
		next := state
		if _, err := next.ToolProgress.settle(history); err != nil {
			return err
		}
		next.Checkpoint, next.Log = checkpoint, committed
		raw, err := json.Marshal(next)
		if err != nil {
			return err
		}
		if err := atomicSessionFile(dir, raw); err != nil {
			return err
		}
		state = next
		return nil
	}
	set := tools.Set{Dir: dir, RunDir: dir, ProcessDir: o.RunDir, Env: node.Environment()}
	childTools := scenarioTools(j, set.All())
	childTools = append(childTools, runtimeCapabilitiesTool(j.Workspace, dir, dir))
	o = contextOptions(o)
	loop := &agent.Loop{
		Directory: dir, SessionDir: dir,
		Provider: provider, Tools: childTools, SaveState: save, ObserveRequests: true,
		ContextBytes:        o.ContextBytes,
		ContextTokens:       o.ContextTokens,
		ContextTargetTokens: o.ContextTargetTokens,
		Emit: func(e agent.Event) {
			if logErr == nil {
				logErr = journal.Append(e)
			}
		},
	}
	loop.BeforeRequest = func(ctx context.Context, loop *agent.Loop) (context.Context, error) {
		pinToolGuidance(loop)
		return ctx, state.ToolProgress.problem()
	}
	loop.OnTurnEnd = func(ctx context.Context, loop *agent.Loop, message agent.Message) (context.Context, string, error) {
		if !hasToolCalls(message) {
			return ctx, "", nil
		}
		if err := state.ToolProgress.problem(); err != nil {
			return ctx, "", err
		}
		if state.ToolProgress.needsCorrection() {
			state.ToolProgress.Warned = true
			if err := save(loop.History, loop.SnapshotCheckpoint()); err != nil {
				state.ToolProgress.Warned = false
				return ctx, "", err
			}
			return ctx, "Recent tools have repeated unchanged observations or kept failing. Change the approach or return a concise account of the blocker and remaining work.", nil
		}
		return ctx, "", nil
	}
	if err := save(nil, nil); err != nil {
		return workergraph.Output{}, err
	}
	text, runErr := loop.Run(ctx, prompt)
	if final, ok := lastAssistant(loop.History); runErr == nil && ok && truncated(final) {
		runErr = errors.New("agent node final response was truncated; inspect its session before retrying")
	}
	if runErr == nil && strings.TrimSpace(text) == "" {
		runErr = errors.New("agent node returned no account of its work")
	}
	// stdout.log is the node's final local account, not its event stream and
	// never a top-level Worker result. Reuse verifies these exact bytes.
	outputContext := ctx
	if runErr != nil {
		// A node timeout ends its work, but the active parent can still
		// receive bounded diagnostics. Parent cancellation stops this read.
		outputContext = parent
	}
	out, outputErr := node.RetainOutput(outputContext, text, runErr == nil)
	runErr = errors.Join(runErr, outputErr)
	state.Result = text
	if runErr != nil {
		state.Error = runErr.Error()
	} else {
		// Only this final save certifies successful completion. Saved assistant
		// history alone may precede tools, output retention or a failed save.
		state.TerminalOutput = &out
	}
	if err := save(loop.History, loop.Checkpoint); err != nil {
		return workergraph.Output{}, errors.Join(runErr, err)
	}
	if runErr != nil {
		// Like a failed command, keep the bounded account for the parent and
		// failure routes, without certifying files from an unsuccessful Agent.
		out.Artifacts = nil
		return out, fmt.Errorf("agent node failed; inspect %s: %w", filepath.Join(dir, "events.jsonl"), runErr)
	}
	return out, nil
}

// Reconciliation consumes an existing terminal receipt without starting a Loop,
// changing its journal or retrying a tool. DAG verifies the returned artifacts
// before accepting this result into its checkpoint.
func reconcileAgentNode(ctx context.Context, j Job, node dag.AgentNode) (workergraph.Output, error) {
	fail := func() (workergraph.Output, error) {
		return workergraph.Output{}, errors.New("agent has no verified bound terminal receipt; inspect its session without replaying work")
	}
	resolved, err := filepath.EvalSymlinks(node.Dir)
	if err != nil || resolved != node.Dir {
		return fail()
	}
	raw, err := readEvidenceFile(ctx, filepath.Join(node.Dir, "session.json"), 32<<20)
	if err != nil {
		return workergraph.Output{}, err
	}
	var state graphAgentSession
	if json.Unmarshal(raw, &state) != nil || state.SchemaVersion != sessionSchemaVersion || state.RunID != j.RunID || state.GraphKey != node.Key || state.NodeID != node.Spec.ID ||
		len(node.InputSHA256) != 64 || state.GraphInputSHA256 != node.InputSHA256 || state.TerminalOutput == nil || state.Error != "" || strings.TrimSpace(state.Result) == "" ||
		state.Checkpoint == nil || state.Checkpoint.Version != agent.ContextCheckpointVersion || len(state.Checkpoint.PiSession) == 0 {
		return fail()
	}
	conversation := &agent.Loop{Directory: node.Dir, SessionDir: node.Dir, Checkpoint: state.Checkpoint}
	if err := conversation.Restore(ctx); err != nil {
		return workergraph.Output{}, err
	}
	if len(conversation.History) == 0 {
		return fail()
	}
	last := conversation.History[len(conversation.History)-1]
	if last.Role != "assistant" || hasToolCalls(last) || truncated(last) || last.Text() != state.Result || last.Sequence != state.Checkpoint.LastSequence {
		return fail()
	}
	var committed agent.Message
	if err := eventlog.VisitCommitted(ctx, filepath.Join(node.Dir, "events.jsonl"), state.Log, func(message agent.Message) error {
		committed = message
		return nil
	}); err != nil {
		return workergraph.Output{}, err
	}
	left, _ := json.Marshal(last)
	right, _ := json.Marshal(committed)
	if string(left) != string(right) {
		return fail()
	}
	out := *state.TerminalOutput
	digest := sha256.Sum256([]byte(state.Result))
	if len(out.Artifacts) == 0 || out.Artifacts[0].Path != filepath.Join(node.Dir, "stdout.log") || out.Artifacts[0].SHA256 != hex.EncodeToString(digest[:]) {
		return fail()
	}
	return out, nil
}
