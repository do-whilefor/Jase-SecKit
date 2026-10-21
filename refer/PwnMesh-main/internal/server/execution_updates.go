package server

import (
	"net/http"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
)

// Reads and filters under one transaction: event boundaries and node versions
// cannot come from different revisions. The HTTP body supplies no source IDs.
func (s *Server) executionUpdates(t *b.Tx, q *request, r *http.Request) (int, any, error) {
	var read protocol.GraphRequest
	if err := decodeStrictFields(q, &read); err != nil || read.Op != "read_updates" {
		return 0, nil, b.Err(422, "expected a read_updates request")
	}
	page, err := execution.ReadUpdates(t, executionReadInput(r, read))
	return http.StatusOK, page, err
}
