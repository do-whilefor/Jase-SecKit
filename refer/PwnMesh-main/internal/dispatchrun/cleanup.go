package dispatchrun

import (
	"context"
	"log/slog"
	"strconv"
	"strings"
	"time"

	board "pwnmesh/internal/board/model"
)

const maxConcurrentCleanups = 8

func (m *Manager) CleanupInactive(ctx context.Context, states map[string]string) error {
	managed, err := m.runner.Projects(ctx)
	if err != nil {
		return err
	}
	start := m.cleanupCursor
	for offset := range managed {
		index := (start + offset) % len(managed)
		id := managed[index]
		state := states[id]
		if state == "active" {
			continue
		}
		if state == "completed" {
			finishing := false
			for _, t := range m.running {
				finishing = finishing || t.Job.Graph.Project.ID == id
			}
			if finishing {
				continue // Let the committed planner return its final observation.
			}
		}
		if state == "" {
			state = "deleted"
		}
		if m.cleaned[id] == state || m.cleanup[id] != "" {
			continue
		}
		if !m.queueCleanup(ctx, id, state) {
			break
		}
		// Failed projects must not monopolize each later admission wave.
		m.cleanupCursor = (index + 1) % len(managed)
	}
	return nil
}

func (m *Manager) queueCleanup(ctx context.Context, id, state string) bool {
	// Track capacity until completion is reaped. Excess projects remain eligible
	// for the next pass, without goroutines waiting for a semaphore slot.
	if ctx.Err() != nil || m.cleanup[id] != "" || len(m.cleanup) >= maxConcurrentCleanups {
		return false
	}
	m.cleanup[id] = state
	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		cleanupCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		err := m.runner.Cleanup(cleanupCtx, id, state)
		select {
		case m.cleanupDone <- cleaned{id, state, err}:
			// A cleanup failure must not trigger its own immediate retry loop.
			if err == nil {
				m.wake()
			}
		case <-ctx.Done():
		}
	}()
	return true
}

// Individual process cancellation is best effort during Docker outages. A
// restart additionally requires a confirmed container stop before any worker
// may enter the new round; this retains the container and workspace files.
func (m *Manager) RestartReady(ctx context.Context, project board.Project) bool {
	if project.Generation == 0 || m.restartCleaned[project.ID] == project.Generation {
		return true
	}
	for _, task := range m.running {
		if task.Job.Graph.Project.ID == project.ID {
			return false
		}
	}
	if m.cleanup[project.ID] == "" {
		m.queueCleanup(ctx, project.ID, "restart:"+strconv.FormatInt(project.Generation, 10))
	}
	return false
}

func (m *Manager) drainCleanup() {
	for {
		select {
		case f := <-m.cleanupDone:
			delete(m.cleanup, f.ID)
			if f.Err == nil {
				m.cleaned[f.ID] = f.State
				if raw, ok := strings.CutPrefix(f.State, "restart:"); ok {
					generation, _ := strconv.ParseInt(raw, 10, 64)
					m.restartCleaned[f.ID] = generation
				}
			} else {
				slog.Warn("container cleanup failed", "project", f.ID, "error", f.Err)
			}
		default:
			return
		}
	}
}
