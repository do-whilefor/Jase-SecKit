//go:build linux

package worker_test

import (
	"encoding/json"
	"strings"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/worker"
)

func snapshotJob(workspace string) worker.Job {
	return worker.Job{
		RunID: "run", Kind: "explore", WorkerType: "pi", GraphRPC: true,
		ResultContractVersion: 2, Workspace: workspace,
		Graph:  board.Graph{Project: board.Project{ID: "project", Generation: 1, OrchestrationVersion: 1}},
		Intent: &board.Intent{ID: "step"}, Budget: board.TaskBudget{ConcludeTimeout: 60},
		InputSnapshot: &board.InputSnapshot{
			Version: 1, ID: strings.Repeat("a", 64), StateVersion: strings.Repeat("b", 64),
			ProjectID: "project", Generation: 1, Revision: 1, StepCount: 1,
		},
		InputView: json.RawMessage(`{"user_inputs":[],"hints":[],"goals":[{"id":"goal","condition":"Inspect the assigned local inputs."}],"steps":[{"id":"step","goal_id":"goal","description":""}]}`),
	}
}
