package dispatcher

import (
	"slices"
	"time"

	board "pwnmesh/internal/board/model"
)

// Coalesce a producer's fact/candidate/final-result burst without waiting
// indefinitely for a long-lived Worker. The persisted cursor is authoritative;
// this timer is only an optimization and can be lost on dispatcher restart.
func (s *Scheduler) waitForCuration(g board.Graph, revision int64, now time.Time) bool {
	id := g.Project.ID
	if !s.producersRunning(g) {
		delete(s.controlConflicts, id)
		return false
	}
	// Keep unacknowledged user input and invalid support urgent until a planner
	// consumes them, even when another ordinary control attempt was stale.
	if s.schedules[id].HintCount > s.checkpoints[id].Hints || s.reasonWaits[id].Urgent {
		return false
	}
	if until, ok := s.controlConflicts[id]; ok {
		return s.waitForControlConflict(until, now)
	}
	if s.curationWaits == nil {
		s.curationWaits = map[string]reasonWait{}
	}
	wait, ok := s.curationWaits[g.Project.ID]
	if !ok {
		wait.First, wait.Changed, wait.Revision = now, now, revision
	} else if wait.Revision != revision {
		wait.Changed, wait.Revision = now, revision
	}
	s.curationWaits[g.Project.ID] = wait
	return s.waitForQuiet(wait, now)
}

func (s *Scheduler) producersRunning(g board.Graph) bool {
	for _, running := range s.runs.Running() {
		if running.ProjectID == g.Project.ID && running.Kind != "reason" && running.Kind != "curate" {
			return true
		}
	}
	return slices.ContainsFunc(s.schedules[g.Project.ID].Steps, func(step board.ScheduleStep) bool { return step.Running })
}

// Only a confirmed stale attempt delays the next ordinary control run beyond
// its usual quiet window. Give the active producer wave time to drain, bounded
// from the failure itself: new observations never extend this deadline. This is
// an ephemeral scheduling optimization; server CAS still decides write safety.
func (s *Scheduler) waitForControlConflict(until, now time.Time) bool {
	if !now.Before(until) {
		return false
	}
	s.wakeAt(until)
	return true
}

// Keep one slot available to control roles when concurrency permits. A
// one-slot installation executes serially; no Worker waits inside its slot
// for another Agent to run.
func (s *Scheduler) executionCapacity(project string) bool {
	executions, projectExecutions := 0, 0
	for _, running := range s.runs.Running() {
		if running.Kind == "reason" || running.Kind == "curate" {
			continue
		}
		executions++
		if running.ProjectID == project {
			projectExecutions++
		}
	}
	return executions < max(1, s.Config.Runtime.MaxWorkers-1) &&
		projectExecutions < max(1, s.Config.Runtime.MaxProjectWorkers-1)
}

func (s *Scheduler) backendExecutionCapacity(name string, limit int) bool {
	for _, backend := range s.Config.Workers {
		if backend.Name != name || !slices.Contains(backend.TaskTypes, "curate") && !slices.Contains(backend.TaskTypes, "reason") {
			continue
		}
		count := 0
		for _, running := range s.runs.Running() {
			if running.Backend == name && running.Kind != "reason" && running.Kind != "curate" {
				count++
			}
		}
		return count < max(1, limit-1)
	}
	return true
}
