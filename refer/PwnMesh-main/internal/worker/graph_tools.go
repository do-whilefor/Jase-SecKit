//go:build linux

package worker

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"pwnmesh/internal/protocol"
	"slices"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/tools"
)

func newRoleRuntime(j Job, config Options, emit agent.Emit) (*roleRuntime, error) {
	if err := validateWorkerProtocol(j); err != nil {
		return nil, err
	}
	runtime := &roleRuntime{emit: emit}
	if j.Kind == "reason" {
		runtime.graph.Version = j.Decision.StateVersion
	}
	if j.Kind == "curate" {
		runtime.graph.Version = j.CurationVersion()
	}
	o := &config

	if j.Kind == "curate" {
		if err := protocol.ValidateCuratorInput(j); err != nil {
			return nil, err
		}
	}
	if o.Output == nil {
		o.Output = io.Discard
	}
	// Appending per-run closures must not overwrite a reused caller-owned
	// backing array: that would route another Worker's reads/writes here.
	o.Tools = slices.Clone(o.Tools)
	request := configureGraphRequest(j, config, runtime, func(ctx context.Context, request GraphRequest) (string, error) {
		return graphRPC(ctx, config.RunDir, config.Output, request)
	})
	runtime.request = request
	if j.Kind == "reason" {
		runtime.decision = &decisionDraft{closureProtocol: j.Decision.ClosureProtocol == 1, request: request}
	}
	if j.Kind == "curate" {
		runtime.curation = &curationCommit{job: j, request: request}
	}
	read := agent.Tool{Definition: agent.Definition{Name: "read_graph", Description: graphReadDescription(j.Kind), Schema: graphReadSchema()}, Execute: agent.TextExecutor(func(ctx context.Context, raw json.RawMessage) (string, error) {
		if runtime.decision != nil && runtime.decision.committed {
			return "", errors.New("decision already committed")
		}
		r, err := graphReadArguments(raw, "read_graph")
		if err != nil {
			return "", err
		}
		result, err := modelGraphRead(ctx, r, request)
		if err == nil && runtime.decision != nil {
			runtime.decision.observeGraphRead(r.Section, result)
		}
		return result, err
	})}
	allowed := protocol.GraphActions(j)
	description := ""
	switch j.Kind {
	case "reason":
		description = graphActionReasonDescription
	case "curate":
		description = graphActionCurateDescription
	default:
		description = graphActionExploreDescription
	}
	if runtime.decision != nil {
		allowed = append(allowed, "complete", "preview", "commit", "reset")
		description += graphActionDraftDescription
		if j.Decision.CompletionAssessment != nil {
			description += graphActionCompletionAssessmentDescription
		}
	} else if j.Kind == "explore" {
		description += "\n- To finish, pass the published Fact ID to finish_step({fact_id:ID})."
	}
	if j.Kind != "curate" {
		description += "\n\n## Idempotency\n\nUse a stable idempotency_key; reuse it only for the exact same action."
	}
	description += graphActionReceiptDescription
	closure := runtime.decision != nil && runtime.decision.closureProtocol
	if closure {
		description += graphActionRootAssessmentDescription
	}
	parameters := graphActionParameterSchema(j.Kind, allowed, closure)
	schema, _ := json.Marshal(parameters)
	action := agent.Tool{Definition: agent.Definition{Name: "graph_action", Description: description, Schema: schema}, Execute: agent.TextExecutor(func(ctx context.Context, raw json.RawMessage) (string, error) {
		if runtime.graph.Conflict != "" {
			return "", errors.New(runtime.graph.Conflict)
		}
		a, gapID, err := graphActionArguments(raw, parameters)
		if err != nil {
			return "", err
		}
		if j.Kind != "curate" && (len(a.IdempotencyKey) == 0 || len(a.IdempotencyKey) > 128) {
			return "", invalidGraphArgument("idempotency_key", "use 1-128 bytes")
		}
		if runtime.curation != nil {
			return runtime.curation.action(ctx, a.Payload)
		}
		if runtime.decision != nil {
			started, before := time.Now(), len(runtime.decision.actions)
			raw, err := runtime.decision.action(ctx, a, runtime.graph.Version, gapID)
			if runtime.emit != nil && (a.Op == "goal" || a.Op == "step" || a.Op == "curation_request" || a.Op == "complete") {
				runtime.emit((decisionOperation{Op: "draft", ElapsedMS: time.Since(started).Milliseconds(), Failed: err != nil, Actions: max(0, len(runtime.decision.actions)-before)}).event())
			}
			return raw, err
		}
		a.IdempotencyKey = j.RunID + ":" + a.IdempotencyKey
		return request(ctx, GraphRequest{Op: "graph_action", Action: a})
	})}
	if protocol.ControlJob(j) {
		o.Tools = []agent.Tool{read, action}
		if runtime.decision != nil && runtime.decision.closureProtocol {
			o.Tools = append(o.Tools, rootAssessmentTool(runtime.decision, func() string { return runtime.graph.Version }))
		}
	} else {
		if o.Tools == nil {
			set := tools.Set{Dir: j.Workspace, RunDir: o.RunDir}
			o.Tools = set.All()
			o.Tools = append(o.Tools, commandGraphTool(j, *o))
		}
		o.Tools = append(o.Tools, read, action)
		runtime.stepFinish = &stepFinish{job: j, runDir: o.RunDir}
		o.Tools = append(o.Tools, runtime.stepFinish.tool(), httpReplayTool(j, *o))
	}
	o.Tools = append(o.Tools, rawEvidenceTool(j, runtime, request), runtimeCapabilitiesTool(j.Workspace, j.Workspace, o.RunDir))
	if protocol.TraceReader(j) {
		o.Tools = append(o.Tools, workerTraceTool(j, o, request))
	}
	o.Tools = scenarioTools(j, o.Tools)
	if j.Kind != "curate" {
		frozen := read
		frozen.Name = "read_snapshot"
		frozen.Description = graphSnapshotDescription
		frozen.Execute = agent.TextExecutor(func(ctx context.Context, raw json.RawMessage) (string, error) {
			r, err := graphReadArguments(raw, "read_snapshot")
			if err != nil {
				return "", err
			}
			return modelGraphRead(ctx, r, request)
		})
		o.Tools = append(o.Tools, frozen)
	}
	runtime.tools = o.Tools
	return runtime, nil
}
