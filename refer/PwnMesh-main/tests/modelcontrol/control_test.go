package modelcontrol_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/config"
	"pwnmesh/internal/kimi"
	"pwnmesh/internal/modelconfig"
	"pwnmesh/internal/modelcontrol"
	"pwnmesh/internal/provider"
	"pwnmesh/internal/server"
)

func setup(t *testing.T) (*b.Store, *modelconfig.Store, *modelcontrol.Client, *httptest.Server) {
	t.Helper()
	t.Setenv("PWNMESH_AUTH_DIR", filepath.Join(t.TempDir(), "credentials"))
	store, err := b.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { store.Close() })
	settings := &modelconfig.Store{Path: filepath.Join(t.TempDir(), "settings.json"), Defaults: modelconfig.Defaults(func(string) string { return "" })}
	client := &modelcontrol.Client{Namespace: "test", Holder: strings.Repeat("a", 32), ControlToken: strings.Repeat("s", 64)}
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		client.Installation, err = tx.InstallationID()
		if err != nil {
			return err
		}
		return tx.DispatcherLease(client.Namespace, client.Holder, client.Installation, "claim")
	}); err != nil {
		t.Fatal(err)
	}
	api := httptest.NewServer(server.NewWithOptions(store, server.Options{ModelSettingsPath: settings.Path, ControlToken: client.ControlToken}))
	t.Cleanup(api.Close)
	client.Base = api.URL
	return store, settings, client, api
}

func TestRuntimeSettingsRequireLiveOwnerAndStayOutOfPublicAPI(t *testing.T) {
	store, settings, client, api := setup(t)
	ctx := context.Background()
	if _, found, err := client.Settings(ctx); err != nil || found {
		t.Fatalf("missing settings: %v %v", found, err)
	}
	if _, err := settings.Update(func(s *modelconfig.Settings) error { s.Token = "private-test-key"; return nil }); err != nil {
		t.Fatal(err)
	}
	got, found, err := client.Settings(ctx)
	if err != nil || !found || got.Token != "private-test-key" {
		t.Fatalf("runtime settings: %v %v", found, err)
	}
	res, err := http.Get(api.URL + "/model-settings")
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := io.ReadAll(res.Body)
	res.Body.Close()
	if bytes.Contains(raw, []byte("private-test-key")) || !bytes.Contains(raw, []byte(`"has_token":true`)) {
		t.Fatal("public settings leaked or lost token state")
	}
	for _, change := range []func(*modelcontrol.Client){
		func(c *modelcontrol.Client) { c.ControlToken = strings.Repeat("z", 64) },
		func(c *modelcontrol.Client) { c.Holder = strings.Repeat("b", 32) },
		func(c *modelcontrol.Client) { c.Installation = "wrong" },
		func(c *modelcontrol.Client) { c.Namespace = "other" },
	} {
		bad := *client
		change(&bad)
		if _, _, err := bad.Settings(ctx); err == nil {
			t.Error("accepted invalid owner")
		}
	}
	req, _ := http.NewRequest("POST", api.URL+modelcontrol.SettingsPath, strings.NewReader("{}"))
	req.Header.Set("Authorization", "Bearer "+client.ControlToken)
	req.Header.Set("X-PwnMesh-Dispatcher", client.Holder)
	req.Header.Set("X-PwnMesh-Namespace", client.Namespace)
	req.Header.Set("X-PwnMesh-Installation", client.Installation)
	req.Header.Set("Origin", api.URL)
	res, err = http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	res.Body.Close()
	if res.StatusCode != 403 {
		t.Fatalf("browser status %d", res.StatusCode)
	}
	if err := store.Do(ctx, func(tx *b.Tx) error {
		return tx.DispatcherLease(client.Namespace, client.Holder, client.Installation, "release")
	}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.Settings(ctx); err == nil {
		t.Fatal("released owner received credentials")
	}
}

func TestExampleTaskBudgetsKeepModelPolicy(t *testing.T) {
	for key, value := range map[string]string{
		"PWNMESH_CONTROL_TOKEN":         strings.Repeat("t", 32),
		"PWNMESH_MODEL_PROTOCOL":        "anthropic",
		"OPENAI_BASE_URL":               "",
		"OPENAI_MODEL":                  "",
		"OPENAI_API_KEY":                "",
		"ANTHROPIC_BASE_URL":            "https://model.invalid",
		"ANTHROPIC_DEFAULT_FABLE_MODEL": "test-model",
		"ANTHROPIC_AUTH_TOKEN":          "test-key",
	} {
		t.Setenv(key, value)
	}
	c, err := config.Load(filepath.Join("..", "..", "dispatch.example.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	example, err := os.ReadFile(filepath.Join("..", "..", "dispatch.example.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	for _, backend := range []string{"go", "pi", "mock"} {
		path := filepath.Join(t.TempDir(), "dispatch.yaml")
		obsolete := strings.Replace(string(example), "  - name: general", "  - name: general\n    type: "+backend, 1)
		if err := os.WriteFile(path, []byte(obsolete), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := config.Load(path); err == nil || !strings.Contains(err.Error(), "field type not found") {
			t.Fatalf("retired backend selector %q was accepted: %v", backend, err)
		}
	}
	for _, tc := range []struct {
		kind                     string
		timeout, concludeTimeout int
	}{{"reason", 900, 0}, {"curate", 900, 0}, {"explore", 0, 180}} {
		t.Run(tc.kind, func(t *testing.T) {
			budget := c.Task(tc.kind)
			if budget.Timeout != tc.timeout || budget.ConcludeTimeout != tc.concludeTimeout {
				t.Fatalf("task budget = %+v, want timeout=%d conclude_timeout=%d", budget, tc.timeout, tc.concludeTimeout)
			}
			for _, worker := range c.Workers {
				p, err := provider.FromEnvironment(context.Background(), worker.Getenv, budget.ReasoningEffort)
				if err != nil {
					t.Fatal(err)
				}
				if p.Timeout != 300*time.Second || p.ReasoningEffort != "max" {
					t.Fatalf("model policy changed: timeout=%s effort=%s", p.Timeout, p.ReasoningEffort)
				}
				if p.Client != nil {
					p.Client.CloseIdleConnections()
				}
			}
		})
	}
}

func TestModelRequestTimeoutDefaultsAndOverrides(t *testing.T) {
	for _, tc := range []struct {
		name, override string
		seconds        int
	}{{"default", "", 300}, {"environment", "90", 90}} {
		t.Run(tc.name, func(t *testing.T) {
			env := map[string]string{"ANTHROPIC_AUTH_TOKEN": "test-key", "PWNMESH_REQUEST_TIMEOUT": tc.override}
			getenv := func(key string) string { return env[key] }
			settings := modelconfig.Defaults(getenv)
			if settings.RequestTimeout != tc.seconds {
				t.Fatalf("settings timeout = %d, want %d", settings.RequestTimeout, tc.seconds)
			}
			for _, values := range []map[string]string{env, settings.Overlay(env)} {
				p, err := provider.FromEnvironment(context.Background(), func(key string) string { return values[key] }, "")
				if err != nil {
					t.Fatal(err)
				}
				if p.Timeout != time.Duration(tc.seconds)*time.Second {
					t.Fatalf("provider timeout = %s, want %ds", p.Timeout, tc.seconds)
				}
				if p.Client != nil {
					p.Client.CloseIdleConnections()
				}
			}
		})
	}
}

func TestModelRequestTimeoutPatchPreservesSettings(t *testing.T) {
	_, settings, client, api := setup(t)
	before, err := settings.Update(func(s *modelconfig.Settings) error {
		s.Token = "private-test-key"
		s.RequestTimeout = 180
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	req, _ := http.NewRequest(http.MethodPut, api.URL+"/model-settings", strings.NewReader(`{"request_timeout":300}`))
	req.Header.Set("Content-Type", "application/json")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var public modelconfig.Public
	if err := json.NewDecoder(res.Body).Decode(&public); err != nil {
		t.Fatal(err)
	}
	if res.StatusCode != http.StatusOK || public.RequestTimeout != 300 || !public.HasToken {
		t.Fatalf("patch status=%d timeout=%d has_token=%v", res.StatusCode, public.RequestTimeout, public.HasToken)
	}
	updated, found, err := client.Settings(context.Background())
	if err != nil || !found {
		t.Fatalf("runtime settings: found=%v err=%v", found, err)
	}
	want := before
	want.RequestTimeout = 300
	if updated != want {
		t.Fatal("timeout patch changed unrelated model settings or was not persisted")
	}
}

func TestOAuthTokensRemainServerOwnedAndRevocable(t *testing.T) {
	_, settings, client, _ := setup(t)
	id := strings.Repeat("c", 32)
	credentials := &kimi.Store{Dir: modelconfig.AuthDir(settings.Path)}
	if err := credentials.Save(id, kimi.Credential{AccessToken: "access-one", RefreshToken: "refresh-private", ExpiresAt: time.Now().Add(time.Hour)}); err != nil {
		t.Fatal(err)
	}
	env := map[string]string{"ANTHROPIC_AUTH_MODE": "kimi_oauth", "ANTHROPIC_BASE_URL": "https://api.kimi.com/coding", "ANTHROPIC_CREDENTIAL_ID": id, "ANTHROPIC_MODEL": "kimi-test"}
	p, err := provider.FromEnvironmentWithCredentials(context.Background(), func(k string) string { return env[k] }, "", func(ctx context.Context, id string) (string, error) {
		// An omitted connection mode uses the same direct policy as defaults.
		return client.Token(ctx, modelcontrol.TokenRequest{CredentialID: id})
	})
	if err != nil {
		t.Fatal(err)
	}
	if p.Token != "access-one" {
		t.Fatal("missing access token")
	}
	if strings.Contains(strings.Join(p.CredentialValues(), ","), "refresh-private") {
		t.Fatal("refresh credential left server")
	}
	if err := credentials.Save(id, kimi.Credential{AccessToken: "access-two", RefreshToken: "refresh-rotated", ExpiresAt: time.Now().Add(time.Hour)}); err != nil {
		t.Fatal(err)
	}
	if token, err := p.TokenSource(context.Background()); err != nil || token != "access-two" {
		t.Fatalf("rotated token: %q %v", token, err)
	}
	if len(p.CredentialValues()) < 3 {
		t.Fatal("earlier access tokens lost from redaction set")
	}
	if err := credentials.Delete(id); err != nil {
		t.Fatal(err)
	}
	if _, err := p.TokenSource(context.Background()); err == nil {
		t.Fatal("revoked credential still available")
	}
}

func TestControlClientRejectsRedirectsAndHidesFailureBodies(t *testing.T) {
	forwarded := false
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { forwarded = true }))
	defer target.Close()
	api := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 307) }))
	defer api.Close()
	client := &modelcontrol.Client{Base: api.URL, Namespace: "test", Holder: strings.Repeat("a", 32), Installation: "test", ControlToken: strings.Repeat("s", 64)}
	if _, _, err := client.Settings(context.Background()); err == nil || forwarded {
		t.Fatal("followed credential redirect")
	}
	failure := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		json.NewEncoder(w).Encode(map[string]string{"secret": "must-not-log"})
	}))
	defer failure.Close()
	client.Base = failure.URL
	if _, _, err := client.Settings(context.Background()); err == nil || strings.Contains(err.Error(), "must-not-log") {
		t.Fatal("unexpected failure disclosure")
	}
}
