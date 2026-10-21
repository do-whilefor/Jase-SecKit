package server

import (
	"net/http"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
)

// Authorize retained process reads using the caller's current execution lease.
// Paths and source identities come from registered Jobs, never model arguments.
func (s *Server) executionTraces(t *b.Tx, q *request, r *http.Request) (int, any, error) {
	var read protocol.GraphRequest
	if err := decodeStrictFields(q, &read); err != nil || read.Op != "read_trace_runs" {
		return 0, nil, b.Err(422, "expected a read_trace_runs request")
	}
	page, err := execution.ReadTraces(t, executionReadInput(r, read))
	return http.StatusOK, page, err
}
