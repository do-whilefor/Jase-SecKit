package worker

import (
	"bytes"
	"embed"
	"encoding/json"
	"errors"
	"os"
	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/protocol"
	"strconv"
	"strings"
	"text/template"
)

//go:embed prompts/*.md
var prompts embed.FS

//go:embed prompts/pentest.md
var pentestPolicy string

//go:embed prompts/audit.md
var auditPolicy string

//go:embed prompts/ctf.md
var ctfPolicy string

//go:embed prompts/ctf_execute.md
var ctfExecution string

const executionDiscipline = `- When acquisition is assigned to a node, that node owns the first request: do not send preliminary connectivity or schema probes; inspect its retained bytes afterward.
- Probes, retries and child tasks share the task's operation limits.`

type promptContext struct {
	Kind                 string
	Orchestration        bool
	Decision             bool
	CompletionAssessment bool
	Graph                string
	Dependencies         string
}

func Prompt(j Job, conclude bool) (string, error) {
	if j.Kind != "explore" && j.Kind != "reason" && j.Kind != "curate" {
		return "", errors.New("unknown task")
	}
	if conclude && protocol.ControlJob(j) {
		return "", errors.New("control roles have no conclusion phase")
	}
	// The original task stays pinned in the session. Phase changes describe only
	// what changed; rebuilding its graph and policy would pin duplicate inputs.
	if conclude {
		return taskTemplate(j, true)
	}
	view, err := jobContextView(j)
	if err != nil {
		return "", err
	}
	input := promptContext{Kind: j.Kind, Orchestration: protocol.OrchestrationJob(j), Graph: string(view)}
	if j.Decision != nil && j.Decision.Version == 2 {
		input.Decision = true
		input.CompletionAssessment = j.Decision.CompletionAssessment != nil
	}
	if protocol.OrchestrationJob(j) && !protocol.ControlJob(j) && len(j.DependencyResults) != 0 {
		dependencies, err := json.Marshal(j.DependencyResults)
		if err != nil {
			return "", err
		}
		input.Dependencies = string(dependencies)
	}
	context, err := renderPrompt("context", input)
	if err != nil {
		return "", err
	}
	body, err := taskTemplate(j, conclude)
	if err != nil {
		return "", err
	}
	assignment := "Current run_id: " + j.RunID
	if intent := intentContext(j, view); intent != "" {
		assignment = strings.TrimPrefix(intent, "\n") + "\n" + assignment
	}
	return environmentPrompt(j) + context + "\n" + body + scenarioPrompt(j) +
		"\n# Current assignment\n\n" + assignment + "\n", nil
}

func environmentPrompt(j Job) string {
	text := "# Environment\n\n"
	// The shipped Kali image declares its capabilities. Other Worker
	// deployments must not inherit claims about that image's installed tools.
	if os.Getenv("PWNMESH_WORKER_ENVIRONMENT") == "kali-headless" {
		text += "- This Worker runs in a Kali Linux container with kali-linux-headless installed.\n"
	}
	text += "- The shared project workspace is " + strconv.Quote(j.Workspace) + "; it can store scripts, command logs and large scan results.\n"
	if !protocol.ControlJob(j) {
		text += executionDiscipline + "\n"
	}
	return text + "\n"
}

func taskTemplate(j Job, conclude bool) (string, error) {
	name := j.Kind
	if conclude {
		name += "_conclude"
	}
	return renderPrompt(name, struct {
		board.TaskBudget
		Orchestration bool
		Retry         bool
	}{j.Budget, protocol.OrchestrationJob(j), j.PreviousRunID != ""})
}

func renderPrompt(name string, data any) (string, error) {
	t, err := template.ParseFS(prompts, "prompts/"+name+".md")
	if err != nil {
		return "", err
	}
	var body bytes.Buffer
	if err = t.Execute(&body, data); err != nil {
		return "", err
	}
	return strings.TrimSpace(body.String()) + "\n", nil
}

func scenarioPrompt(j Job) string {
	if j.Kind == "curate" {
		return ""
	}
	switch j.Graph.Project.Scenario {
	case "pentest":
		return "\n" + pentestPolicy
	case "audit":
		return "\n" + auditPolicy
	case "ctf":
		return "\n" + ctfPolicy
	}
	return ""
}

func intentContext(j Job, view []byte) string {
	if j.Intent == nil {
		return ""
	}
	// Only omit text already supplied in full. Bounded views without
	// the matching Step still need the original assignment as a fallback.
	var input struct {
		Steps []struct {
			ID            string `json:"id"`
			Description   string `json:"description"`
			RecordOmitted bool   `json:"record_omitted"`
		} `json:"steps"`
	}
	if json.Unmarshal(view, &input) == nil {
		for _, step := range input.Steps {
			if step.ID == j.Intent.ID && step.Description == j.Intent.Description && !step.RecordOmitted {
				return "\nCurrent Step: " + j.Intent.ID + " (see task_graph)."
			}
		}
	}
	return "\nCurrent intent " + j.Intent.ID + ": " + j.Intent.Description
}

func jobContextView(j Job) ([]byte, error) {
	if err := protocol.ValidateSnapshotInput(j); err != nil {
		return nil, err
	}
	if j.Kind == "curate" {
		if err := protocol.ValidateCuratorInput(j); err != nil {
			return nil, err
		}
	}
	if j.Kind == "reason" {
		return json.Marshal(j.Decision)
	}
	return j.InputView, nil
}
