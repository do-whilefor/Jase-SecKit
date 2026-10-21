package dispatcher

import (
	"context"
	"errors"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/protocol"
)

func (s *Scheduler) scheduleInput(ctx context.Context, id string) (board.SchedulePage, error) {
	var input board.SchedulePage
	for offset := 0; ; {
		query := controlclient.ScheduleQuery{Offset: offset, Namespace: s.namespace()}
		if offset > 0 {
			query.ExpectedVersion = input.StateVersion
		}
		page, err := s.Client.Schedule(ctx, id, query)
		if err != nil {
			return input, err
		}
		if offset == 0 {
			input = page
		} else {
			if page.StateVersion != input.StateVersion || page.Project.Generation != input.Project.Generation {
				return input, &protocol.RPCError{Code: board.CodeStateChanged, Status: 409, Detail: "state_changed: scheduling pages do not match"}
			}
			input.Steps = append(input.Steps, page.Steps...)
			for key, check := range page.ExecutionChecks {
				if input.ExecutionChecks == nil {
					input.ExecutionChecks = map[string]board.ExecutionCheck{}
				}
				input.ExecutionChecks[key] = check
			}
		}
		if page.NextOffset == 0 {
			return input, nil
		}
		if page.NextOffset <= offset {
			return input, errors.New("scheduling cursor did not advance")
		}
		offset = page.NextOffset
	}
}
