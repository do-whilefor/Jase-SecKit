//go:build linux && !headless

package main

import (
	"net/http"
	"pwnmesh/internal/httpui"
	"pwnmesh/web"
)

func withUI(api http.Handler) http.Handler { return httpui.Mount(api, web.Files) }
