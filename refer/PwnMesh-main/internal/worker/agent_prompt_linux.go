//go:build linux

package worker

import (
	"encoding/json"
	"errors"
	"fmt"
	"slices"

	"pwnmesh/internal/worker/dag"
)

type agentPromptContext struct {
	Directory           string
	Workspace           string
	ExecutionDiscipline string
	Constraints         string
	Scenario            string
	Task                string
	Artifacts           string
	Dependencies        string
}

// Child guidance uses the parent's bound assignment and frozen dependencies.
// Session execution and recovery do not own prompt text or context projection.
func agentNodePrompt(j Job, dir string, spec dag.Node, constraints string, views []dag.NodeView) (string, error) {
	var artifacts string
	if len(spec.Artifacts) != 0 {
		encoded, err := json.Marshal(spec.Artifacts)
		if err != nil {
			return "", err
		}
		artifacts = string(encoded)
	}
	return renderPrompt("agent", agentPromptContext{
		Directory: dir, Workspace: j.Workspace, ExecutionDiscipline: executionDiscipline,
		Constraints: constraints, Scenario: scenarioPrompt(j), Task: spec.Task,
		Artifacts: artifacts, Dependencies: agentDependencySnapshot(views),
	})
}

// Derive child constraints from the parent's bound input, not a fresh graph
// read. Keep original wording and supplied prerequisite evidence, excluding
// unrelated work. Evidence remains task data with its original limitations.
func agentAssignmentContext(j Job) (string, error) {
	raw, err := jobContextView(j)
	if err != nil {
		return "", err
	}
	type goalConstraint struct {
		ID        string `json:"id"`
		ParentID  string `json:"parent_id,omitempty"`
		Condition string `json:"condition"`
	}
	var view struct {
		UserInputs json.RawMessage   `json:"user_inputs"`
		Hints      json.RawMessage   `json:"hints"`
		Steps      []json.RawMessage `json:"steps"`
		Goals      []goalConstraint  `json:"goals"`
		agentAssignedEvidence
		Related agentAssignedEvidence `json:"related"`
	}
	if err := json.Unmarshal(raw, &view); err != nil {
		return "", err
	}
	var step map[string]json.RawMessage
	if j.Intent != nil {
		for _, candidate := range view.Steps {
			var id struct{ ID string }
			if err := json.Unmarshal(candidate, &id); err != nil {
				return "", err
			}
			if id.ID == j.Intent.ID {
				if err := json.Unmarshal(candidate, &step); err != nil {
					return "", err
				}
				break
			}
		}
		if step == nil {
			return "", errors.New("child assignment is missing its Step from the immutable input")
		}
		for field := range step {
			switch field {
			case "id", "from", "goal_id", "description", "assessment", "reason", "dispute_id", "depends_on", "write_paths", "repair":
			default:
				delete(step, field)
			}
		}
	}
	var goals []goalConstraint
	if step != nil {
		var goalID string
		if raw, ok := step["goal_id"]; ok {
			if err := json.Unmarshal(raw, &goalID); err != nil {
				return "", err
			}
		}
		if goalID == "" {
			return "", errors.New("child assignment is missing its Step goal from the immutable input")
		}
		byID := make(map[string]goalConstraint, len(view.Goals))
		for _, goal := range view.Goals {
			byID[goal.ID] = goal
		}
		seen := map[string]bool{}
		for goalID != "" {
			if seen[goalID] {
				return "", errors.New("child assignment has cyclic goal ancestry")
			}
			goal, ok := byID[goalID]
			if !ok {
				return "", fmt.Errorf("child assignment is missing goal %q from the bound input", goalID)
			}
			goals = append(goals, goal)
			seen[goalID] = true
			goalID = goal.ParentID
		}
		// ContextView also retains the root goal when the selected ancestry
		// does not reach it; it still constrains the parent's assignment.
		if root, ok := byID["goal"]; ok && !seen[root.ID] {
			goals = append(goals, root)
		}
	}
	var assignment struct {
		From      []string `json:"from"`
		DependsOn []string `json:"depends_on"`
	}
	bound, _ := json.Marshal(step)
	if err := json.Unmarshal(bound, &assignment); err != nil {
		return "", err
	}
	selected := map[string]bool{}
	for _, id := range assignment.From {
		selected[id] = true
	}
	for _, result := range j.DependencyResults {
		if slices.Contains(assignment.DependsOn, result.StepID) {
			selected[result.FactID] = true
		}
	}
	var inputs []struct{ ID string }
	if err := json.Unmarshal(view.UserInputs, &inputs); err != nil {
		return "", err
	}
	for _, input := range inputs {
		delete(selected, input.ID)
	}
	evidence, err := selectAgentEvidence(selected, view.agentAssignedEvidence, view.Related)
	if err != nil {
		return "", err
	}
	encoded, err := json.Marshal(struct {
		UserInputs json.RawMessage            `json:"user_inputs"`
		Hints      json.RawMessage            `json:"hints"`
		Step       map[string]json.RawMessage `json:"step,omitempty"`
		Goals      []goalConstraint           `json:"goals,omitempty"`
		agentAssignedEvidence
	}{view.UserInputs, view.Hints, step, goals, evidence})
	return string(encoded), err
}

type agentAssignedEvidence struct {
	Facts     []json.RawMessage `json:"fact_records,omitempty"`
	Relations []json.RawMessage `json:"fact_relations,omitempty"`
	Missing   []string          `json:"omitted_fact_ids,omitempty"`
}

// Select only bound prerequisites and their supplied corrections from the
// bounded parent view, adding IDs for missing support. There is no new graph
// query or evidence summary; original records keep their explicit omissions.
func selectAgentEvidence(selected map[string]bool, supplied ...agentAssignedEvidence) (agentAssignedEvidence, error) {
	type fact struct {
		ID             string   `json:"id"`
		DetailsOmitted bool     `json:"details_omitted"`
		DerivedFrom    []string `json:"derived_from"`
	}
	type relation struct{ Kind, Source, Target string }
	facts := map[string]json.RawMessage{}
	omitted := map[string]bool{}
	derived := map[string][]string{}
	relations := map[string]relation{}
	for _, source := range supplied {
		for _, raw := range source.Facts {
			var item fact
			if err := json.Unmarshal(raw, &item); err != nil {
				return agentAssignedEvidence{}, err
			}
			prior, exists := facts[item.ID]
			if !exists || omitted[item.ID] && !item.DetailsOmitted || omitted[item.ID] == item.DetailsOmitted && len(raw) > len(prior) {
				facts[item.ID], omitted[item.ID] = raw, item.DetailsOmitted
				derived[item.ID] = item.DerivedFrom
			}
		}
		for _, raw := range source.Relations {
			var item relation
			if err := json.Unmarshal(raw, &item); err != nil {
				return agentAssignedEvidence{}, err
			}
			relations[string(raw)] = item
		}
	}
	for changed := true; changed; {
		changed = false
		for _, item := range relations {
			if slices.Contains([]string{"supersedes", "refutes", "narrows"}, item.Kind) && (selected[item.Source] || selected[item.Target]) {
				changed = changed || !selected[item.Source] || !selected[item.Target]
				selected[item.Source], selected[item.Target] = true, true
			}
		}
		for id := range selected {
			for _, source := range derived[id] {
				if !selected[source] {
					selected[source], changed = true, true
				}
			}
		}
	}
	ids := make([]string, 0, len(selected))
	for id := range selected {
		ids = append(ids, id)
	}
	slices.Sort(ids)
	result := agentAssignedEvidence{}
	for _, id := range ids {
		if raw, ok := facts[id]; ok {
			result.Facts = append(result.Facts, raw)
		} else {
			result.Missing = append(result.Missing, id)
		}
	}
	keys := []string{}
	for raw, item := range relations {
		if selected[item.Source] && selected[item.Target] {
			keys = append(keys, raw)
		}
	}
	slices.Sort(keys)
	for _, raw := range keys {
		result.Relations = append(result.Relations, json.RawMessage(raw))
	}
	return result, nil
}

// Small dependency results are already available to the runtime, so let a
// child reason from them in its first request. Large fan-ins remain file-based;
// never silently truncate an output or crowd out the child's task and tools.
func agentDependencySnapshot(dependencies []dag.NodeView) string {
	const limit = 16 << 10
	if len(dependencies) == 0 {
		return ""
	}
	type dependency struct {
		ID     string         `json:"id"`
		Kind   string         `json:"kind"`
		Status string         `json:"status"`
		Output dag.OutputView `json:"output"`
		Error  string         `json:"error,omitempty"`
		Reason string         `json:"reason,omitempty"`
	}
	snapshot := make([]dependency, 0, len(dependencies))
	size := 0
	for _, dep := range dependencies {
		// This lower bound avoids encoding an entire large fan-in only to
		// discard it. The final check also counts JSON syntax and escaping.
		size += len(dep.ID) + len(dep.Kind) + len(dep.Status) + len(dep.Output.Value) + len(dep.Error) + len(dep.Reason)
		for _, artifact := range dep.Output.Artifacts {
			size += len(artifact.Path) + len(artifact.SHA256)
		}
		if size > limit {
			return ""
		}
		snapshot = append(snapshot, dependency{dep.ID, dep.Kind, dep.Status, dep.Output, dep.Error, dep.Reason})
	}
	raw, err := json.Marshal(snapshot)
	if err != nil || len(raw) > limit {
		return ""
	}
	return string(raw)
}
