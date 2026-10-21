package protocol

import (
	"errors"
	"pwnmesh/internal/board/model"
)

func ControlJob(j Job) bool { return j.Kind == "reason" || j.Kind == "curate" }

func OrchestrationJob(j Job) bool { return j.Graph.Project.OrchestrationVersion == 1 }

func GraphActions(j Job) []string {
	switch j.Kind {
	case "curate":
		return []string{"curate"}
	case "reason":
		return []string{"goal", "step", "curation_request"}
	case "explore":
		return []string{"fact", "candidate"}
	default:
		return nil
	}
}

func ValidateCuratorInput(j Job) error {
	if !OrchestrationJob(j) || !j.GraphRPC || j.Intent != nil || j.Decision != nil {
		return errors.New("curate requires protocol 1, a live bridge and an immutable state without an intent or decision")
	}
	return ValidateSnapshotInput(j)
}

// InputBinding exposes the shared immutable boundary without changing Job JSON.
func (j Job) InputBinding() model.JobInputBinding {
	return model.JobInputBinding{Graph: j.Graph, State: j.State, InputSnapshot: j.InputSnapshot}
}

func (j Job) CurationVersion() string { return j.InputBinding().StateVersion() }

func (j Job) CurationRevision() int64 { return j.InputBinding().Revision() }
