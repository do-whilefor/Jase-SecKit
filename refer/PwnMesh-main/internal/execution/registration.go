// Package execution composes scheduling, reads, preparation and settlement in
// a caller-owned Board transaction, without HTTP or transaction-finalization access.
package execution

import (
	"encoding/json"
	b "pwnmesh/internal/board"
	"pwnmesh/internal/protocol"
)

// Execution inputs always use the live evidence protocol.
func validateExecutionProtocol(graphRPC, resultVersion json.RawMessage) error {
	var enabled bool
	if json.Unmarshal(graphRPC, &enabled) != nil || !enabled {
		return b.Err(422, "graph_rpc must be true")
	}
	var version int
	if json.Unmarshal(resultVersion, &version) != nil || version != 2 {
		return b.Err(422, "result_contract_version must be 2")
	}
	return nil
}

func requireCurrentExecution(e b.Execution) error {
	var job protocol.Job
	if json.Unmarshal(e.Job, &job) != nil || job.Graph.Project.OrchestrationVersion != 1 || !job.GraphRPC || job.ResultContractVersion != 2 || job.Kind != e.Kind || (e.Kind != "reason" && e.Kind != "curate" && e.Kind != "explore") || (e.Kind == "reason" && (job.Decision == nil || job.Decision.Version != 2)) {
		return b.Err(409, "Unsupported execution protocol; create a new project to continue")
	}
	if err := protocol.ValidateSnapshotInput(job); err != nil {
		return b.Err(409, err.Error())
	}
	return nil
}
