//go:build linux && headless

package main

import "net/http"

func withUI(api http.Handler) http.Handler { return api }
