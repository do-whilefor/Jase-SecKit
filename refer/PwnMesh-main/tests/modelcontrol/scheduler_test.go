package modelcontrol_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/config"
	"pwnmesh/internal/dispatcher"
	"pwnmesh/internal/modelconfig"
	"pwnmesh/internal/modelcontrol"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/provider"
)

func TestTransientCredentialFailureDoesNotBecomeConfigurationFailure(t *testing.T) {
	for _, failure := range []string{"rate_limit", "truncated_body"} {
		t.Run(failure, func(t *testing.T) {
			store, settings, client, api := setup(t)
			if _, err := settings.Update(func(s *modelconfig.Settings) error {
				s.AuthMode = "kimi_oauth"
				s.BaseURL = "https://api.kimi.com/coding"
				s.CredentialID = strings.Repeat("c", 32)
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			if err := store.Do(context.Background(), func(tx *b.Tx) error {
				return tx.DispatcherLease(client.Namespace, client.Holder, client.Installation, "release")
			}); err != nil {
				t.Fatal(err)
			}
			failing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == modelcontrol.TokenPath {
					if failure == "truncated_body" {
						w.Header().Set("Content-Length", "100")
						_, _ = w.Write([]byte(`{"token":"private-fragment`))
					} else {
						w.WriteHeader(503)
						_, _ = w.Write([]byte(`{"kind":"rate_limit","status":429}`))
					}
					return
				}
				api.Config.Handler.ServeHTTP(w, r)
			}))
			defer failing.Close()
			c := config.Config{Server: failing.URL, ModelSettingsSource: "server", ControlToken: client.ControlToken, Container: config.Container{Namespace: client.Namespace},
				Runtime: config.Runtime{MaxWorkers: 1, MaxProjects: 1, HealthTimeout: 5}, Workers: []config.Worker{{Name: "go"}}}
			s := dispatcher.New(c, &idleRunner{})
			err := s.StartupHealth(context.Background())
			if err == nil || !strings.Contains(err.Error(), "model readiness transient") || strings.Contains(err.Error(), "private-fragment") {
				t.Fatalf("refresh failure classification: %v", err)
			}
		})
	}
}

type idleRunner struct {
	factory func(context.Context, config.Worker, protocol.Job) (*provider.Client, error)
}

func (*idleRunner) Run(context.Context, config.Worker, protocol.Job) (protocol.Result, error) {
	panic("health must not start work")
}
func (*idleRunner) Cleanup(context.Context, string, string) error {
	panic("health must not clean workspaces")
}
func (*idleRunner) Projects(context.Context) ([]string, error) {
	panic("health must not inspect workspaces")
}
func (r *idleRunner) SetModelFactory(f func(context.Context, config.Worker, protocol.Job) (*provider.Client, error)) {
	r.factory = f
}

func TestDispatcherLoadsServerSettingsWithoutSharedFiles(t *testing.T) {
	store, settings, client, _ := setup(t)
	if _, err := settings.Update(func(s *modelconfig.Settings) error { s.Token = "runtime-key"; return nil }); err != nil {
		t.Fatal(err)
	}
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		return tx.DispatcherLease(client.Namespace, client.Holder, client.Installation, "release")
	}); err != nil {
		t.Fatal(err)
	}
	runner := &idleRunner{}
	c := config.Config{Server: client.Base, ModelSettingsSource: "server", ControlToken: client.ControlToken,
		ModelSettingsPath: "/missing-and-unmounted/settings.json", Container: config.Container{Namespace: client.Namespace},
		Runtime: config.Runtime{MaxWorkers: 1, MaxProjects: 1}, Workers: []config.Worker{{Name: "go", Env: map[string]string{"ANTHROPIC_AUTH_TOKEN": "fallback"}}}}
	s := dispatcher.New(c, runner)
	checked := false
	s.CheckHealth = func(ctx context.Context, w config.Worker) error {
		checked = true
		if w.Env["ANTHROPIC_AUTH_TOKEN"] != "runtime-key" {
			t.Fatal("did not receive server settings")
		}
		p, err := runner.factory(ctx, w, protocol.Job{})
		if err != nil {
			return err
		}
		if !strings.Contains(strings.Join(p.CredentialValues(), ","), client.ControlToken) {
			t.Fatal("control token missing from launch redaction")
		}
		tools, err := w.ToolEnvironment()
		if err != nil {
			return err
		}
		for _, v := range tools {
			if v == "runtime-key" || v == client.ControlToken {
				t.Fatal("credentials entered tools")
			}
		}
		return nil
	}
	if err := s.StartupHealth(context.Background()); err != nil {
		t.Fatal(err)
	}
	if !checked {
		t.Fatal("health did not run")
	}
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		return tx.DispatcherLease(client.Namespace, client.Holder, client.Installation, "claim")
	}); err != nil {
		t.Fatal(err)
	}
}

func TestModelSettingsSourceIsExplicitAndControlTokenNeverReachesTools(t *testing.T) {
	t.Setenv(modelconfig.PathEnv, "")
	path := filepath.Join(t.TempDir(), "bad-settings.json")
	if err := os.WriteFile(path, []byte("invalid"), 0600); err != nil {
		t.Fatal(err)
	}
	base := config.Config{Server: "http://server:8000", ControlToken: strings.Repeat("s", 64), ModelSettingsSource: "server", ModelSettingsPath: path,
		Runtime:   config.Runtime{Interval: 2, MaxWorkers: 1, MaxProjects: 1, MaxProjectWorkers: 1, HealthTimeout: 5},
		Tasks:     config.Tasks{Explore: config.Task{ConcludeTimeout: 5}},
		Container: config.Container{Image: "worker", Network: "bridge", CompletedAction: "stop"},
		Workers:   []config.Worker{{Name: "go", MaxRunning: 1, TaskTypes: []string{"reason", "curate", "explore"}}}}
	if err := base.Validate(); err != nil {
		t.Fatalf("server source touched local file: %v", err)
	}
	base.ModelSettingsSource = "file"
	if err := base.Validate(); err == nil {
		t.Fatal("file source ignored invalid settings")
	}
	w := config.Worker{Env: map[string]string{"PWNMESH_CONTROL_TOKEN": "private", "TOOL_SETTING": "retained"}}
	tools, err := w.ToolEnvironment()
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := tools["PWNMESH_CONTROL_TOKEN"]; ok || tools["TOOL_SETTING"] != "retained" {
		t.Fatal("incorrect tool environment isolation")
	}
}
