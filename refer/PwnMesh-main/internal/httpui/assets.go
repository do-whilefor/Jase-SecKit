// Package httpui mounts optional browser assets around an independent API.
package httpui

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"net/http"
	"strings"
	"time"
)

func Mount(api http.Handler, assets fs.FS) http.Handler {
	if assets == nil {
		return api
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /static", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/static/", http.StatusTemporaryRedirect)
	})
	mux.HandleFunc("GET /static/", func(w http.ResponseWriter, r *http.Request) {
		name := strings.TrimPrefix(r.URL.Path, "/static/")
		data, err := fs.ReadFile(assets, name)
		if err != nil {
			writeError(w, http.StatusNotFound, "Not Found")
			return
		}
		http.ServeContent(w, r, name, time.Time{}, bytes.NewReader(data))
	})
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		data, err := fs.ReadFile(assets, "index.html")
		if err != nil {
			http.Error(w, "Web unavailable", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(data)
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Preserve ServeMux's escaped-path matching and canonical redirects.
		if _, pattern := mux.Handler(r); pattern != "" {
			mux.ServeHTTP(w, r)
			return
		}
		probe := r.Clone(r.Context())
		probe.Method = http.MethodGet
		if _, pattern := mux.Handler(probe); pattern != "" {
			w.Header().Set("Allow", "GET, HEAD")
			writeError(w, http.StatusMethodNotAllowed, "Method Not Allowed")
			return
		}
		api.ServeHTTP(w, r)
	})
}

func writeError(w http.ResponseWriter, status int, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"code": "request_failed", "detail": detail})
}
