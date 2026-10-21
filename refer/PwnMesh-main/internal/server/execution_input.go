package server

import (
	"net/http"
	"strconv"

	b "pwnmesh/internal/board"
	"pwnmesh/internal/execution"
	"pwnmesh/internal/protocol"
)

func (s *Server) schedulingInput(t *b.Tx, _ *request, r *http.Request) (int, any, error) {
	versions := r.URL.Query()["protocol_version"]
	if len(versions) != 1 || versions[0] != strconv.Itoa(b.ScheduleProtocolVersion) {
		return 0, nil, b.Err(422, "scheduling protocol mismatch: Server requires protocol_version="+strconv.Itoa(b.ScheduleProtocolVersion)+"; upgrade Server and Dispatcher together")
	}
	offset := 0
	if raw := r.URL.Query().Get("offset"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n < 0 {
			return 0, nil, b.Err(422, "invalid scheduling offset")
		}
		offset = n
	}
	input := execution.ScheduleQuery{ProjectID: r.PathValue("pid"), Offset: offset, ExpectedVersion: r.URL.Query().Get("expected_version")}
	if r.URL.Query().Has("namespace") {
		namespace := r.URL.Query().Get("namespace")
		input.Namespace = &namespace
	}
	page, err := execution.Schedule(t, input)
	return http.StatusOK, page, err
}

// HTTP supplies project identity and the lease; the use case freezes its input.
func (s *Server) prepareExecution(t *b.Tx, q *request, r *http.Request) (int, any, error) {
	var template b.Execution
	if err := decodeFields(q, &template); err != nil {
		return 0, nil, b.Err(422, "invalid execution template")
	}
	template.ProjectID = r.PathValue("pid")
	prepared, err := execution.PrepareRun(t, template, decisionFence(r))
	status := http.StatusOK
	if prepared.Created {
		status = http.StatusCreated
	}
	return status, prepared.Execution, err
}

func (s *Server) snapshotRead(t *b.Tx, q *request, r *http.Request) (int, any, error) {
	var read protocol.GraphRequest
	if err := decodeStrictFields(q, &read); err != nil || read.Op != "read_snapshot" {
		return 0, nil, b.Err(422, "expected a read_snapshot request")
	}
	page, err := execution.ReadSnapshot(t, executionReadInput(r, read))
	return http.StatusOK, page, err
}

func executionReadInput(r *http.Request, read protocol.GraphRequest) execution.ReadInput {
	return execution.ReadInput{ProjectID: r.PathValue("pid"), RunID: r.PathValue("rid"), Fence: decisionFence(r), Request: read}
}
