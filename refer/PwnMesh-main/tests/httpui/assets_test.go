package httpui_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/fstest"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/httpui"
	"pwnmesh/internal/server"
)

func TestOptionalAssetsLeaveAPIIndependent(t *testing.T) {
	store, err := b.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	api := server.NewWithOptions(store, server.Options{})
	assets := fstest.MapFS{"index.html": {Data: []byte("<!doctype html><title>PwnMesh</title>")}, "assets/app.js": {Data: []byte("export default 1;")}}
	for _, c := range []struct {
		name, path string
		handler    http.Handler
		status     int
	}{
		{"api health", "/health", api, 200}, {"api root", "/", api, 404},
		{"nil assets", "/", httpui.Mount(api, nil), 404},
		{"embedded root", "/", httpui.Mount(api, assets), 200},
		{"asset", "/static/assets/app.js", httpui.Mount(api, assets), 200},
		{"missing asset", "/static/missing", httpui.Mount(api, assets), 404},
		{"traversal", "/static/../index.html", httpui.Mount(api, assets), 404},
		{"embedded health", "/health", httpui.Mount(api, assets), 200},
	} {
		t.Run(c.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			c.handler.ServeHTTP(w, httptest.NewRequest("GET", c.path, nil))
			if w.Code != c.status {
				t.Fatalf("status %d: %s", w.Code, w.Body.String())
			}
		})
	}
}

func TestWorkspaceViewPreservesExistingJSONAndStateIdentity(t *testing.T) {
	store, err := b.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	var state b.State
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		g, err := tx.CreateProject(b.ProjectInput{Title: "View", Origin: "Fixture", Goal: "Stable JSON"})
		if err != nil {
			return err
		}
		state, err = tx.State(g.Project.ID)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	before := b.DecisionStateVersion(state)
	w := httptest.NewRecorder()
	server.NewWithOptions(store, server.Options{}).ServeHTTP(w, httptest.NewRequest("GET", "/projects/"+state.Graph.Project.ID+"/state", nil))
	expected, _ := json.Marshal(state)
	if w.Code != 200 || !bytes.Equal(bytes.TrimSpace(w.Body.Bytes()), expected) {
		t.Fatalf("view changed JSON: %d %s", w.Code, w.Body.String())
	}
	if b.DecisionStateVersion(state) != before {
		t.Fatal("presentation changed frozen state identity")
	}
}

func TestAssetRoutesPreserveMethodsAndCanonicalPaths(t *testing.T) {
	api := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNotFound) })
	assets := fstest.MapFS{"index.html": {Data: []byte("<!doctype html><title>PwnMesh</title>")}, "assets/app.js": {Data: []byte("export default 1;")}}
	handler := httpui.Mount(api, assets)
	for _, test := range []struct {
		method, path, allow, location string
		status                        int
	}{
		{"POST", "/", "GET, HEAD", "", 405},
		{"PUT", "/static", "GET, HEAD", "", 405},
		{"OPTIONS", "/static/assets/app.js", "GET, HEAD", "", 405},
		{"DELETE", "/static/missing", "GET, HEAD", "", 405},
		{"GET", "/static", "", "/static/", 307},
		{"GET", "/static//assets/app.js?version=1", "", "/static/assets/app.js?version=1", 307},
		{"GET", "/static/assets/../assets/app.js", "", "/static/assets/app.js", 307},
	} {
		t.Run(test.method+" "+test.path, func(t *testing.T) {
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, httptest.NewRequest(test.method, test.path, nil))
			if w.Code != test.status || w.Header().Get("Allow") != test.allow || w.Header().Get("Location") != test.location {
				t.Fatalf("response %d, Allow=%q Location=%q: %s", w.Code, w.Header().Get("Allow"), w.Header().Get("Location"), w.Body.String())
			}
			if test.status == 405 && w.Body.String() != "{\"code\":\"request_failed\",\"detail\":\"Method Not Allowed\"}\n" {
				t.Errorf("method error changed: %s", w.Body.String())
			}
		})
	}
}

func TestMissingIndexKeepsUnavailableResponse(t *testing.T) {
	api := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNotFound) })
	w := httptest.NewRecorder()
	httpui.Mount(api, fstest.MapFS{}).ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Code != 500 || w.Body.String() != "Web unavailable\n" || w.Header().Get("Content-Type") != "text/plain; charset=utf-8" {
		t.Fatalf("missing index changed: %d %s %s", w.Code, w.Header().Get("Content-Type"), w.Body.String())
	}
}

func TestBrowserGuardPrecedesMountedAssetMethodErrors(t *testing.T) {
	api := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNotFound) })
	assets := fstest.MapFS{"index.html": {Data: []byte("<!doctype html><title>PwnMesh</title>")}}
	handler := server.BrowserGuard(httpui.Mount(api, assets))
	for _, path := range []string{"/", "/static", "/static/assets/app.js"} {
		r := httptest.NewRequest("POST", path, nil)
		r.Header.Set("Origin", "https://other.example")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != 403 || w.Header().Get("Allow") != "" {
			t.Errorf("%s: %d, Allow=%q: %s", path, w.Code, w.Header().Get("Allow"), w.Body.String())
		}
	}
}

func TestWorkspaceViewPreservesNonemptyAssetJSONOrder(t *testing.T) {
	store, err := b.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	var state b.State
	if err := store.Do(context.Background(), func(tx *b.Tx) error {
		graph, err := tx.CreateProject(b.ProjectInput{Title: "Assets", Origin: "Fixture", Goal: "Stable JSON"})
		if err != nil {
			return err
		}
		graph.Intents = append(graph.Intents, b.Intent{ID: "i1", From: []string{"origin"}, Description: "Inspect fixture", Creator: "test", Worker: b.Ptr("fixture"), Heartbeat: b.Ptr(tx.Now), CreatedAt: tx.Now})
		if err = tx.Save(graph); err != nil {
			return err
		}
		payload, err := json.Marshal(map[string]any{
			"description": "Observed host", "scope": "fixture", "observed_at": tx.Now,
			"evidence": []b.EvidenceRef{{RunID: "fixture", Path: "/workspace/evidence.txt", Excerpt: "observed"}},
			"assets":   []b.AssetSpec{{Kind: "host", Value: "example.com"}},
		})
		if err != nil {
			return err
		}
		_, err = tx.StateAction(graph.Project.ID, b.ExecutionFence{Run: "fixture", Lease: "explore", Intent: "i1"}, b.StateAction{Op: "fact", IdempotencyKey: "asset-fixture", Payload: payload})
		if err != nil {
			return err
		}
		state, err = tx.State(graph.Project.ID)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if len(state.Assets) == 0 || len(state.AssetAnchors) == 0 {
		t.Fatal("fixture has no assets")
	}
	before := b.DecisionStateVersion(state)
	w := httptest.NewRecorder()
	server.NewWithOptions(store, server.Options{}).ServeHTTP(w, httptest.NewRequest("GET", "/projects/"+state.Graph.Project.ID+"/state", nil))
	expected, _ := json.Marshal(state)
	if w.Code != 200 || !bytes.Equal(bytes.TrimSpace(w.Body.Bytes()), expected) {
		t.Fatalf("asset view changed JSON: %d %s", w.Code, w.Body.String())
	}
	if b.DecisionStateVersion(state) != before {
		t.Fatal("presentation changed frozen state identity")
	}
}
