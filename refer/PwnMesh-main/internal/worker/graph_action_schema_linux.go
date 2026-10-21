package worker

import (
	"encoding/json"
	"fmt"
	"maps"
	"slices"
	"strings"

	"pwnmesh/internal/artifactcheck"
	board "pwnmesh/internal/board/model"
)

const evidenceSelectionDescription = "For new evidence, select a UTF-8 file at most 32 MiB by path; selected content must be nonempty and at most 8192 bytes. " +
	"Omit both line bounds for the whole file, or supply start_line and end_line together (1-based, inclusive). Omit excerpt; the runtime captures the selected bytes."
const factScopeDescription = "For a fact, preserve any task-specified scope value exactly; put additional explanation in description."

func graphTextLimitDescription(name string, field map[string]any) map[string]any {
	if maximum := board.StateTextMaxBytes(name); maximum > 0 {
		field = maps.Clone(field)
		description, _ := field["description"].(string)
		field["description"] = strings.TrimSpace(description + fmt.Sprintf(" At most %d UTF-8 bytes.", maximum))
	}
	return field
}

func graphReadSchema() json.RawMessage {
	sections := []string{"overview", "facts", "goals", "steps", "findings", "relations", "hints", "evidence", "sources", "candidates", "disputes", "assets", "anchors", "history", "related"}
	raw, _ := json.Marshal(map[string]any{
		"type": "object", "properties": map[string]any{
			"section": map[string]any{
				"type": "string", "enum": sections,
				"description": `Record sections support listing.

- evidence and sources require exactly one ID to select its support.
- related returns bounded evidence, associated attempts and judgment reasons from step_id, query, fact ids or asset_ids; no offset.`,
			},
			"ids": map[string]any{
				"type": "array", "items": map[string]any{"type": "string"}, "maxItems": 50, "uniqueItems": true,
				"description": "Exactly one owning record ID (Fact, Finding or Candidate) is required for evidence or sources. " +
					"Fact sources returns derived_from. Other sections may omit IDs to list records.",
			},
			"asset_ids": map[string]any{
				"type": "array", "items": map[string]any{"type": "string", "minLength": 1, "maxLength": 256}, "maxItems": 32, "uniqueItems": true,
				"description": "Match any of these assets in assets/anchors/facts/steps/findings/candidates/history. Combine with ids to narrow records.",
			},
			"asset_neighborhood": map[string]any{
				"type": "boolean",
				"description": "Optional with asset_ids: include syntax-defined ancestors/descendants, never siblings or DNS aliases. " +
					"Asset reads expose ancestor_ids host/service selectors; only stored records are returned.",
			},
			"step_id": map[string]any{
				"type": "string", "maxLength": 256,
				"description": "related only: inspect this Step's inputs, retained result and associated attempts.",
			},
			"assessment": map[string]any{
				"type":        "object",
				"description": "related only: find prior or active checks of this exact claim/scope, even when all earlier checks have ended.",
				"properties": map[string]any{
					"claim": map[string]any{"type": "string", "minLength": 1, "maxLength": 16384},
					"scope": map[string]any{"type": "string", "minLength": 1, "maxLength": 4096},
				}, "required": []string{"claim", "scope"}, "additionalProperties": false,
			},
			"query": map[string]any{
				"type": "string", "maxLength": 1024,
				"description": "related only: a short question or exact identifying terms. Returns bounded evidence and paths.",
			},
			"offset": map[string]any{"type": "integer", "minimum": 0},
			"limit":  map[string]any{"type": "integer", "minimum": 1, "maximum": 50},
		}, "required": []string{"section"}, "additionalProperties": false,
	})
	return raw
}

// Shared field descriptions are projected into the operation-specific schemas
// below. State-dependent semantics remain with the draft/server validators.
func orchestrationPayloadSchema(kind string) map[string]any {
	text := map[string]any{"type": "string"}
	nonempty := map[string]any{"type": "string", "minLength": 1, "pattern": `\S`}
	if kind == "reason" {
		properties := map[string]any{"description": map[string]any{
			"type": "string",
			"description": "Step add: name the unanswered question and required evidence. " +
				"For parallel checks, explain the distinct evidence source or method, or the need for independent verification.",
		}}
		properties["id"] = map[string]any{"type": "string", "description": "Existing record to change. Omit on goal/step add; the server assigns IDs. Use the draft key for $aliases."}
		properties["parent_id"] = text
		properties["condition"] = map[string]any{"type": "string", "description": "Goal add only. Put Step requirements and acceptance checks in description."}
		properties["from"] = map[string]any{
			"type": "array", "items": text,
			"description": `- Step inputs: published, effective Fact IDs or origin.
- Complete: published, effective Fact IDs only, never origin.
- goal is a user constraint, never a source; assign a Goal with goal_id instead.`,
		}
		properties["goal_id"] = map[string]any{"type": "string", "description": "The Goal this Step advances; use goal for the root requirement. Never put this ID in from."}
		properties["priority"] = map[string]any{"type": "integer", "minimum": 0, "maximum": 1000000}
		properties["action"] = map[string]any{
			"type": "string", "enum": []string{"add", "achieve", "withdraw", "abandon", "priority", "retry"},
			"description": `Only goal and step use action:

- goal: add/achieve/withdraw.
- step: add/abandon/priority/retry.
- Complete uses from and description without action; the root goal is completed only by complete.
- step retry requires only id, latest_run_id and reason and authorizes one new execution after failure.`,
		}
		properties["latest_run_id"] = map[string]any{"type": "string", "description": "Required for step retry; copy the target Step's latest_run_id to bind the observed failed attempt."}
		properties["dispute_id"] = map[string]any{"type": "string", "description": "Assign an independent review Step with a new execution. Include both sides' raw sources and a specific question in description."}
		properties["repair"] = artifactcheck.Schema()
		properties["assessment"] = map[string]any{
			"type": "object",
			"description": "Optional immutable step add contract. Give coordinated checks the same canonical proposition and scope; " +
				"producers use that exact claim/scope with verified/refuted/candidate status.",
			"properties": map[string]any{"claim": graphTextLimitDescription("claim", nonempty), "scope": graphTextLimitDescription("scope", nonempty)}, "required": []string{"claim", "scope"}, "additionalProperties": false,
		}
		properties["assets"] = assetInputSchema()
		properties["depends_on"] = map[string]any{
			"type": "array", "items": text, "uniqueItems": true,
			"description": "Optional step add prerequisites: existing Step IDs or earlier Step $aliases, never Fact IDs. Use from for evidence inputs.",
		}
		properties["write_paths"] = map[string]any{
			"type": "array", "maxItems": 16,
			"items": map[string]any{"type": "string", "minLength": 1, "maxLength": 4096},
			"description": "Optional immutable step add output files or directories under /workspace, outside /workspace/.pwnmesh. " +
				"Declare shared writes; overlapping scopes run sequentially. repair.path is included automatically.",
		}
		properties["sources"] = map[string]any{
			"type": "array", "items": text,
			"description": `- Goal achievement support.
- For curation_request, provide 1-32 unique published, effective observation Fact IDs; never origin, goal or draft aliases.
- Reopening needs_review must retain its original source IDs, even if invalidated; additional sources must be effective.`,
		}
		properties["reason"] = map[string]any{
			"type": "string",
			"description": `Explain the action.

- For a low-yield step retry, identify the changed method or prerequisite.
- For curation_request, state the concrete evidence conflict or merge requiring Curate; its payload uses only sources and reason.`,
		}
		return map[string]any{"type": "object", "properties": properties, "additionalProperties": false}
	}
	if kind != "curate" {
		return map[string]any{"type": "object", "properties": map[string]any{
			"assets":          assetInputSchema(),
			"asset_relations": assetRelationInputSchema(),
			"description":     text,
			"reason":          text,
			"sources":         map[string]any{"type": "array", "items": text},
			"scope":           map[string]any{"type": "string", "description": factScopeDescription},
			"observed_at":     map[string]any{"type": "string", "format": "date-time"},
			"context":         observationContextSchema(),
			"derived_from":    factDerivationSchema(),
			"claim":           text,
			"status": map[string]any{
				"type": "string", "enum": []string{"candidate", "verified", "refuted"},
				"description": "Optional producer judgment; omitted means a tentative candidate, never a shared conclusion.",
			},
			"supersedes": map[string]any{
				"type": "string",
				"description": "Optional active Candidate ID from this run with the same claim and scope. " +
					"Supply current support; earlier evidence, reasoning and judgment remain in history.",
			},
			"evidence": map[string]any{
				"type": "array",
				"items": map[string]any{
					"type": "object", "description": evidenceSelectionDescription,
					"properties": map[string]any{
						"path": text,
						// Historical references remain valid for Findings backed by sources.
						"run_id":     text,
						"excerpt":    text,
						"start_line": map[string]any{"type": "integer"},
						"end_line":   map[string]any{"type": "integer"},
					}, "required": []string{"path"}, "additionalProperties": false,
				},
			},
		}}
	}
	return map[string]any{"type": "object", "properties": map[string]any{
		"request_review": map[string]any{
			"type": "object",
			"description": `Required for an unreviewed explicit curation request. Record its outcome and every requested source.
Omit this field when processing unrelated groups while an existing needs_review stays blocked.`,
			"properties": map[string]any{
				"disposition":     map[string]any{"type": "string", "enum": []string{"resolved", "no_change", "needs_review"}},
				"checked_sources": map[string]any{"type": "array", "items": text, "minItems": 1, "maxItems": 32, "uniqueItems": true},
				"reason":          graphTextLimitDescription("reason", nonempty),
			}, "required": []string{"disposition", "checked_sources", "reason"}, "additionalProperties": false,
		},
		"relations": map[string]any{"type": "array", "maxItems": board.MaxCurationRelations, "items": map[string]any{
			"type": "object", "properties": map[string]any{
				"kind":   map[string]any{"type": "string", "enum": []string{"supersedes", "refutes", "narrows"}},
				"source": nonempty, "target": nonempty, "reason": graphTextLimitDescription("reason", nonempty),
			}, "required": []string{"kind", "source", "target", "reason"}, "additionalProperties": false,
		}},
		"groups": map[string]any{
			"type": "array", "maxItems": 128,
			"description": `Supply up to 128 complete pending groups per commit. Select exactly one per group:

- group_key: all active notes in that group.
- candidate_ids: the complete group, at most 256 IDs.`,
			"items": map[string]any{
				"type": "object", "properties": map[string]any{
					"candidate_ids": map[string]any{"type": "array", "items": text, "minItems": 1, "maxItems": 256, "uniqueItems": true},
					"group_key":     map[string]any{"type": "string", "minLength": 1, "description": "Use the exact group_key returned on a Candidate; the server selects every active member."},
					"status":        map[string]any{"type": "string", "enum": []string{"candidate", "verified", "refuted"}},
					"reason":        graphTextLimitDescription("reason", nonempty), "question": graphTextLimitDescription("question", text), "dispute_id": map[string]any{"type": []string{"string", "null"}},
					"review_fact_ids": map[string]any{"type": []string{"array", "null"}, "items": text, "uniqueItems": true, "description": "Independent review evidence for an existing dispute only; omit for ordinary corroboration."},
					"resolution":      map[string]any{"type": []string{"string", "null"}, "enum": []any{"resolved", "uncertain", nil}, "description": "Only for an existing dispute; include its dispute_id."},
				}, "required": []string{"status", "reason"}, "oneOf": []any{map[string]any{"required": []string{"candidate_ids"}}, map[string]any{"required": []string{"group_key"}}}, "additionalProperties": false,
			},
		},
	}, "required": []string{"groups"}, "additionalProperties": false}
}

type graphActionShape struct {
	op, transition, fields, required string
}

func graphActionShapes(kind string) []graphActionShape {
	switch kind {
	case "reason":
		return []graphActionShape{
			{"goal", "add", "action parent_id condition", "action condition"},
			{"goal", "achieve", "action id reason sources", "action id reason sources"},
			{"goal", "withdraw", "action id reason", "action id reason"},
			{"step", "add", "action goal_id from description priority dispute_id repair assessment assets depends_on write_paths", "action from description"},
			{"step", "abandon", "action id reason", "action id reason"},
			{"step", "priority", "action id reason priority", "action id reason"},
			{"step", "retry", "action id latest_run_id reason", "action id latest_run_id reason"},
			{"curation_request", "", "sources reason", "sources reason"},
			{"complete", "", "from description", "from description"},
			{"preview", "", "", ""}, {"commit", "", "", ""}, {"reset", "", "", ""},
		}
	case "curate":
		return []graphActionShape{{"curate", "", "groups relations request_review", "groups"}}
	default:
		return []graphActionShape{
			{"fact", "", "description scope observed_at context evidence assets derived_from asset_relations", "description scope observed_at evidence"},
			{"candidate", "", "claim scope status supersedes sources evidence reason assets", "claim scope reason"},
		}
	}
}

func graphActionParameterSchema(kind string, allowed []string, closure bool) map[string]any {
	fields := orchestrationPayloadSchema(kind)["properties"].(map[string]any)
	properties := map[string]any{
		"op":              map[string]any{"type": "string", "enum": allowed},
		"idempotency_key": map[string]any{"type": "string", "minLength": 1, "maxLength": 128},
		"payload":         map[string]any{"type": "object"},
	}
	required := []string{"op", "idempotency_key"}
	if kind == "curate" {
		delete(properties, "idempotency_key")
		required = []string{"op", "payload"}
	}
	if closure {
		properties["gap_id"] = map[string]any{"type": "string", "minLength": 1, "description": "A missing requirement gap returned by assess_root."}
	}
	branches := []any{}
	for _, shape := range graphActionShapes(kind) {
		if !slices.Contains(allowed, shape.op) {
			continue
		}
		payloadFields := map[string]any{}
		for _, name := range strings.Fields(shape.fields) {
			payloadFields[name] = graphTextLimitDescription(name, fields[name].(map[string]any))
		}
		if shape.transition != "" {
			payloadFields["action"] = map[string]any{"type": "string", "enum": []string{shape.transition}}
		}
		payload := map[string]any{"type": "object", "properties": payloadFields, "additionalProperties": false}
		if shape.required != "" {
			payload["required"] = strings.Fields(shape.required)
			for _, name := range strings.Fields(shape.required) {
				field := maps.Clone(payloadFields[name].(map[string]any))
				if field["type"] == "array" && name != "groups" {
					field["minItems"] = 1
				}
				payloadFields[name] = field
			}
		}
		branchProperties := maps.Clone(properties)
		branchProperties["op"] = map[string]any{"enum": []string{shape.op}}
		branchProperties["payload"] = payload
		delete(branchProperties, "gap_id")
		if kind == "reason" && shape.fields != "" {
			branchProperties["idempotency_key"] = map[string]any{
				"type": "string", "minLength": 1, "maxLength": 64, "pattern": `^[A-Za-z][A-Za-z0-9_-]{0,63}$`,
			}
		}
		branch := map[string]any{"type": "object", "properties": branchProperties, "additionalProperties": false}
		branchRequired := []string{}
		if shape.fields != "" {
			branchRequired = append(branchRequired, "payload")
		}
		if closure && (shape.transition == "add" || shape.transition == "retry" || shape.op == "curation_request") {
			branchProperties["gap_id"] = properties["gap_id"]
			branchRequired = append(branchRequired, "gap_id")
		}
		if len(branchRequired) > 0 {
			branch["required"] = branchRequired
		}
		branches = append(branches, branch)
	}
	return map[string]any{"type": "object", "properties": properties, "required": required, "additionalProperties": false, "oneOf": branches}
}
