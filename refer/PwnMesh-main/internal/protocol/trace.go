package protocol

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"path/filepath"
	"strings"

	"pwnmesh/internal/board/model"
)

// TraceReader grants only the observation projection, never another role's
// tools or graph write authority. Source executions remain Explore-only.
func TraceReader(j Job) bool {
	if !j.GraphRPC || j.RunID == "" || j.Graph.Project.ID == "" {
		return false
	}
	switch j.Kind {
	case "explore":
		return j.Intent != nil && j.Intent.ID != ""
	case "reason":
		return j.Intent == nil && j.Decision != nil && j.Decision.Version == 2
	case "curate":
		return ValidateCuratorInput(j) == nil
	default:
		return false
	}
}

func validateTraceRunRequest(j Job, r GraphRequest) error {
	if !TraceReader(j) {
		return errors.New("trace reads require a registered Explore, Reason or Curate bridge")
	}
	// A zero StateAction encodes payload:null when crossing the bridge.
	mutation := r.Action.Op != "" || r.Action.IdempotencyKey != "" || r.Action.ExpectedVersion != "" ||
		len(r.Action.Payload) != 0 && strings.TrimSpace(string(r.Action.Payload)) != "null"
	if mutation || r.Section != "" || r.ByteOffset != nil || r.ExpectedVersion != "" || r.RecordVersion != "" ||
		r.Updates != nil || r.Batch != nil || r.Query != "" || r.StepID != "" || r.Assessment != nil ||
		len(r.IDs) > 1 || r.Offset < 0 || r.Limit < 0 || r.Limit > 20 {
		return errors.New("trace reads accept only one run ID or an offset/limit page")
	}
	if len(r.IDs) == 1 && (strings.TrimSpace(r.IDs[0]) == "" || len(r.IDs[0]) > 256 || strings.ContainsAny(r.IDs[0], "/\\\x00") || r.IDs[0] == "." || r.IDs[0] == ".." || r.Offset != 0) {
		return errors.New("trace run must identify a registered execution in the current project")
	}
	return nil
}

// BindTraceRun runs on the server before a trace descriptor crosses the bridge.
// Execution.Job can have map-canonical field ordering after HTTP decoding;
// session identity instead hashes the decoded, typed Worker Job serialization.
func BindTraceRun(run model.TraceRun) (model.TraceRun, error) {
	var j Job
	if json.Unmarshal(run.RegisteredJob, &j) != nil || j.Kind != "explore" || j.RunID != run.RunID || j.Graph.Project.ID != run.ProjectID || j.Graph.Project.Generation != run.Generation || j.Workspace != run.Workspace || j.Intent == nil || j.Intent.ID != run.StepID {
		return model.TraceRun{}, errors.New("trace unavailable: registered execution identity mismatch")
	}
	// runSession normalizes this field before calling identityFor.
	var err error
	j.Workspace, err = filepath.Abs(j.Workspace)
	if err != nil {
		return model.TraceRun{}, err
	}
	run.Workspace = j.Workspace
	raw, err := json.Marshal(j)
	if err != nil {
		return model.TraceRun{}, err
	}
	digest := sha256.Sum256(raw)
	run.JobSHA256, run.RegisteredJob = hex.EncodeToString(digest[:]), nil
	return run, nil
}
