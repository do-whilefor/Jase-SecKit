package dispatcher

import (
	"context"
	"maps"

	"pwnmesh/internal/config"
	"pwnmesh/internal/modelconfig"
	"pwnmesh/internal/modelcontrol"
	"pwnmesh/internal/protocol"
	"pwnmesh/internal/provider"
)

// Called only by the scheduler loop. Existing tasks own their earlier Env map;
// new assignments see the replacement map at the next scheduling tick.
func (s *Scheduler) refreshModelSettings(ctx context.Context) error {
	var settings modelconfig.Settings
	var found bool
	var err error
	if s.Config.ModelSettingsSource == "server" {
		settings, found, err = s.runtimeModels.Settings(ctx)
	} else {
		settings, found, err = modelconfig.Read(s.Config.ModelSettingsPath)
	}
	if err != nil {
		return err
	}
	if s.modelLoaded && settings == s.modelSettings {
		return nil
	}
	var overlay *modelconfig.Settings
	if found {
		overlay = &settings
	}
	changed := false
	for n := range s.Config.Workers {
		previous := s.Config.Workers[n]
		next := previous.WithModelSettings(overlay)
		changed = changed || !maps.Equal(previous.Env, next.Env)
		s.Config.Workers[n] = next
	}
	s.modelSettings = settings
	s.modelLoaded = true
	if changed {
		clear(s.incompatible)
		clear(s.unhealthy)
		clear(s.rejected)
	}
	return nil
}

// A completion from an older launch must not poison or clear the new model's
// readiness gate. Tokens participate here even though execution IDs omit them.
func (s *Scheduler) currentModelSettings(w config.Worker) bool {
	if s.Config.ModelSettingsSource != "server" && s.Config.ModelSettingsPath == "" {
		return true
	}
	for _, current := range s.Config.Workers {
		if current.Name != w.Name {
			continue
		}
		for _, key := range []string{"PWNMESH_MODEL_PROTOCOL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "ANTHROPIC_AUTH_MODE", "ANTHROPIC_CREDENTIAL_ID", "ANTHROPIC_CREDENTIAL_DIR", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL", "PWNMESH_REASONING_EFFORT", "PWNMESH_MAX_OUTPUT_TOKENS", "PWNMESH_REQUEST_TIMEOUT", "PWNMESH_CONNECTION_MODE", "PWNMESH_PROXY_URL", "PWNMESH_OPENAI_REASONING_CONTENT"} {
			if current.Env[key] != w.Env[key] {
				return false
			}
		}
		return true
	}
	return false
}

func (s *Scheduler) modelForWorker(ctx context.Context, w config.Worker, effort string) (*provider.Client, error) {
	return workerModel(ctx, w, effort, s.Config.ModelSettingsSource, s.runtimeModels, s.Config.ControlToken)
}

func workerModel(ctx context.Context, w config.Worker, effort, settingsSource string, control *modelcontrol.Client, token string) (*provider.Client, error) {
	var source provider.CredentialSource
	if settingsSource == "server" {
		source = func(ctx context.Context, id string) (string, error) {
			return control.Token(ctx, modelcontrol.TokenRequest{CredentialID: id, ConnectionMode: w.Getenv("PWNMESH_CONNECTION_MODE"), ProxyURL: w.Getenv("PWNMESH_PROXY_URL")})
		}
	}
	p, err := provider.FromEnvironmentWithCredentials(ctx, w.Getenv, effort, source)
	if err != nil {
		return nil, err
	}
	if token != "" {
		previous := p.Secrets
		p.Secrets = func() []string {
			values := []string{token}
			if previous != nil {
				values = append(values, previous()...)
			}
			return values
		}
	}
	return p, nil
}

func (s *Scheduler) configureModelFactory() {
	if runner, ok := s.Runner.(interface {
		SetModelFactory(func(context.Context, config.Worker, protocol.Job) (*provider.Client, error))
	}); ok {
		runner.SetModelFactory(func(ctx context.Context, w config.Worker, j protocol.Job) (*provider.Client, error) {
			return s.modelForWorker(ctx, w, j.Budget.ReasoningEffort)
		})
	}
}
