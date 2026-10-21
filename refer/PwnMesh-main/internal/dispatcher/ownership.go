package dispatcher

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"

	"pwnmesh/internal/modelcontrol"
)

// Fake/in-process runners need no Docker ownership. Container runners bind to
// the authoritative database before any startup cleanup or scheduling tick.
func (s *Scheduler) bindOwnership(ctx context.Context) error {
	runner, ok := s.Runner.(interface{ BindOwner(string) error })
	if !ok {
		return nil
	}
	id, err := s.Client.Installation(ctx)
	if err != nil {
		return err
	}
	return runner.BindOwner(id)
}

func (s *Scheduler) acquireDispatcher(ctx context.Context) (context.Context, func(), error) {
	s.configureModelFactory()
	// In-process test runners do not own or clean Docker namespaces.
	if _, ok := s.Runner.(interface{ BindOwner(string) error }); !ok && s.Config.ModelSettingsSource != "server" {
		return ctx, func() {}, nil
	}
	id, err := s.Client.Installation(ctx)
	if err != nil {
		return nil, nil, err
	}
	if runner, ok := s.Runner.(interface{ BindOwner(string) error }); ok {
		if err := runner.BindOwner(id); err != nil {
			return nil, nil, err
		}
	}
	var token [16]byte
	if _, err := rand.Read(token[:]); err != nil {
		return nil, nil, err
	}
	holder := hex.EncodeToString(token[:])
	if err := s.Client.DispatcherLease(ctx, s.namespace(), holder, id, "claim"); err != nil {
		return nil, nil, err
	}
	s.runtimeModels = &modelcontrol.Client{Base: s.Config.Server, Namespace: s.namespace(), Holder: holder, Installation: id, ControlToken: s.Config.ControlToken}
	owned, cancel := context.WithCancelCause(ctx)
	done := make(chan struct{})
	go func() {
		defer close(done)
		tick := time.NewTicker(5 * time.Second)
		defer tick.Stop()
		for {
			select {
			case <-owned.Done():
				return
			case <-tick.C:
				call, stop := context.WithTimeout(owned, 3*time.Second)
				err := s.Client.DispatcherLease(call, s.namespace(), holder, id, "heartbeat")
				stop()
				if err != nil {
					cancel(fmt.Errorf("dispatcher ownership lost: %w", err))
					return
				}
			}
		}
	}()
	return owned, func() {
		cancel(context.Canceled)
		<-done
		call, stop := context.WithTimeout(context.Background(), 3*time.Second)
		defer stop()
		_ = s.Client.DispatcherLease(call, s.namespace(), holder, id, "release")
	}, nil
}

// StartupHealth uses the same authenticated configuration channel as Run, but
// never performs container cleanup or starts work.
func (s *Scheduler) StartupHealth(ctx context.Context) error {
	owned, release, err := s.acquireDispatcher(ctx)
	if err != nil {
		return err
	}
	defer release()
	return s.Health(owned, true)
}
