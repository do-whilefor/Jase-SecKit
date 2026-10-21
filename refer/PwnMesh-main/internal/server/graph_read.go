package server

import (
	"net/http"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
)

// Apply continuation boundaries before sending the current FGS over HTTP.
// This keeps one oversized Fact from preventing all live graph reads.
func (s *Server) graphRead(t *b.Tx, q *request, r *http.Request) (int, any, error) {
	var read protocol.GraphRequest
	if err := decodeStrictFields(q, &read); err != nil || read.Op != "read_graph" {
		return 0, nil, b.Err(422, "expected a read_graph request")
	}
	page, err := execution.ReadGraph(t, executionReadInput(r, read))
	return http.StatusOK, page, err
}
