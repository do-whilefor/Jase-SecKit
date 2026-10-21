package dispatcher

import (
	"context"
	"log/slog"
	"time"

	board "pwnmesh/internal/board/model"
)

func (s *Scheduler) reconcileProjects(ctx context.Context) (map[string]string, []board.Summary, error) {
	summaries, err := s.Client.List(ctx)
	if err != nil {
		return nil, nil, err
	}
	states := map[string]string{}
	active := []board.Summary{}
	for _, p := range summaries {
		s.observeGeneration(p.Project)
		states[p.ID] = p.Status
		if p.Status == "active" {
			active = append(active, p)
			if _, ok := s.checkpoints[p.ID]; !ok && p.Working+p.Unclaimed > 0 {
				s.checkpoints[p.ID] = checkpoint{p.FactCount, p.HintCount, p.Working + p.Unclaimed}
			}
		}
	}
	for id := range s.admitted {
		if states[id] != "active" {
			delete(s.admitted, id)
			delete(s.checkpoints, id)
		}
	}
	for id := range s.reasonWaits {
		if states[id] != "active" {
			delete(s.reasonWaits, id)
		}
	}
	for id := range s.curationWaits {
		if states[id] != "active" {
			delete(s.curationWaits, id)
		}
	}
	for id := range s.controlConflicts {
		if states[id] != "active" {
			delete(s.controlConflicts, id)
		}
	}
	s.runs.Reconcile(ctx, summaries)
	return states, active, nil
}

func (s *Scheduler) reap() {
	for _, f := range s.runs.Drain() {
		// Retained results can retry delivery indefinitely, but a Server
		// outage must not turn completion wakeups into an immediate loop.
		if f.Outcome == "interrupted" && f.Execution.Status == "result_pending" {
			s.deliveryWaits[f.Job.RunID] = time.Now().Add(5 * time.Second)
		} else {
			delete(s.deliveryWaits, f.Job.RunID)
		}
		if f.Outcome == "failed" && f.UrgentInput && f.Job.Graph.Project.Generation == s.generations[f.Job.Graph.Project.ID] {
			id := f.Job.Graph.Project.ID
			wait := s.reasonWaits[id]
			wait.Urgent = true
			s.reasonWaits[id] = wait
		}
		if f.Outcome == "failed" && !f.StaleInputAt.IsZero() && f.Job.Graph.Project.Generation == s.generations[f.Job.Graph.Project.ID] {
			id, until := f.Job.Graph.Project.ID, f.StaleInputAt.Add(reasonMaxWait)
			if until.After(s.controlConflicts[id]) {
				s.controlConflicts[id] = until
			}
		}
		key := s.rejectKey(f.Job.Graph.Project.ID, f.Job.Kind, f.Worker.Name)
		if s.currentModelSettings(f.Worker) {
			if f.Outcome == "unhealthy" {
				s.recordHealth(f.Worker.Name, f.Err)
			} else {
				delete(s.unhealthy, f.Worker.Name)
			}
		}
		if f.Outcome == "rejected" {
			s.rejected[key] = time.Now().Add(5 * time.Second)
		} else {
			delete(s.rejected, key)
		}
		if f.Outcome == "success" && f.Job.Kind == "reason" && f.Job.Graph.Project.Generation == s.generations[f.Job.Graph.Project.ID] {
			g := f.Job.Graph
			s.checkpoints[g.Project.ID] = checkpoint{len(g.Facts), len(g.Hints), g.OpenCount()}
			if ref := f.Job.InputSnapshot; ref != nil {
				s.checkpoints[g.Project.ID] = checkpoint{ref.FactCount, ref.HintCount, ref.OpenCount}
			}
			s.decisionRevisions[g.Project.ID] = f.Job.DecisionRevision
		}
		if f.Job.Kind != "reason" && f.Job.Kind != "curate" {
			slog.Info("task finished", "project", f.Job.Graph.Project.ID, "run", f.Job.RunID, "task", f.Job.Kind, "outcome", f.Outcome, "error", f.Err)
		}
	}
}

// Restart keeps the project ID but replaces its execution round. Forget the
// prior planner boundary, including when a restart raced the list request.
func (s *Scheduler) observeGeneration(project board.Project) {
	if s.generations == nil {
		s.generations = map[string]int64{}
	}
	if s.generations[project.ID] != project.Generation {
		delete(s.checkpoints, project.ID)
		delete(s.decisionRevisions, project.ID)
		delete(s.schedules, project.ID)
		delete(s.reasonWaits, project.ID)
		delete(s.curationWaits, project.ID)
		delete(s.controlConflicts, project.ID)
		s.generations[project.ID] = project.Generation
	}
}
