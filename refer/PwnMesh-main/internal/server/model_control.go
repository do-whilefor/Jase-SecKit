package server

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/kimi"
	"pwnmesh/internal/modelauth"
	"pwnmesh/internal/modelconfig"
	"pwnmesh/internal/modelcontrol"
	"pwnmesh/internal/provider"
)

func (s *Server) modelControlOwner(r *http.Request) error {
	// Browser routes must never expose the runtime credential channel, even
	// when called from this origin. Ownership is checked independently of UI.
	if r.Header.Get("Origin") != "" || r.Header.Get("Sec-Fetch-Site") != "" {
		return b.Err(403, "model control is restricted to the dispatcher")
	}
	auth := r.Header.Get("Authorization")
	if len(s.controlToken) < 32 || !strings.HasPrefix(auth, "Bearer ") || subtle.ConstantTimeCompare([]byte(strings.TrimPrefix(auth, "Bearer ")), []byte(s.controlToken)) != 1 {
		return b.Err(403, "dispatcher control authentication is required")
	}
	return s.Store.View(r.Context(), func(t *b.Tx) error {
		return t.CheckDispatcherOwner(r.Header.Get("X-PwnMesh-Namespace"), r.Header.Get("X-PwnMesh-Dispatcher"), r.Header.Get("X-PwnMesh-Installation"))
	})
}

func (s *Server) registerModelControl(m *http.ServeMux, path string) {
	m.HandleFunc("POST "+modelcontrol.SettingsPath, func(w http.ResponseWriter, r *http.Request) {
		if err := s.modelControlOwner(r); err != nil {
			writeError(w, r, err)
			return
		}
		settings, found, err := modelconfig.Read(path)
		if err != nil {
			writeError(w, r, b.Err(503, "model settings unavailable"))
			return
		}
		settings.CredentialDir = ""
		modelJSON(w, modelcontrol.Snapshot{Settings: settings, Found: found})
	})
	m.HandleFunc("POST "+modelcontrol.TokenPath, func(w http.ResponseWriter, r *http.Request) {
		if err := s.modelControlOwner(r); err != nil {
			writeError(w, r, err)
			return
		}
		var input modelcontrol.TokenRequest
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		decoder.DisallowUnknownFields()
		if decoder.Decode(&input) != nil || decoder.Decode(new(any)) != io.EOF || !modelauth.ValidCredentialID(input.CredentialID) {
			writeError(w, r, b.Err(422, "invalid credential request"))
			return
		}
		httpClient, err := provider.ConnectionClient(input.ConnectionMode, input.ProxyURL)
		if err != nil {
			writeError(w, r, b.Err(422, "invalid credential connection"))
			return
		}
		if httpClient != nil {
			defer httpClient.CloseIdleConnections()
		}
		credentials := kimi.Store{Dir: modelconfig.AuthDir(path), Client: &kimi.Client{HTTP: httpClient}}
		credential, err := credentials.Resolve(r.Context(), input.CredentialID)
		if err != nil {
			kind, status := "storage", 0
			var failure *kimi.Error
			if errors.As(err, &failure) {
				kind, status = failure.Kind, failure.Status
			}
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Cache-Control", "no-store")
			w.WriteHeader(http.StatusServiceUnavailable)
			_ = json.NewEncoder(w).Encode(map[string]any{"kind": kind, "status": status})
			return
		}
		// Refresh may take time; a lost lease cannot receive its result.
		if err := s.modelControlOwner(r); err != nil {
			writeError(w, r, err)
			return
		}
		modelJSON(w, modelcontrol.TokenResponse{Token: credential.AccessToken})
	})
}
