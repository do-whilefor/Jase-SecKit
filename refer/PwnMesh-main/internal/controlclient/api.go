// Package controlclient adapts the Server HTTP protocol to execution operations.
package controlclient

import (
	"context"
	"encoding/json"
	"io"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/protocol"
)

type Lease struct {
	Run, Kind, Intent string
}

type ScheduleQuery struct {
	Namespace, ExpectedVersion string
	Offset                     int
}

type CurationReceipt struct {
	board.StateActionResult
	ExecutionStatus string `json:"execution_status"`
}

// GraphServer is the authority needed by a launch-bound graph gateway.
type GraphServer interface {
	ExecutionIdentity(context.Context, string, string, string) (board.ExecutionSummary, error)
	CurationReceipt(context.Context, string, Lease) (CurationReceipt, error)
	Decision(context.Context, string, string, *board.DecisionBatch, Lease) (board.DecisionReceipt, error)
	ReadGraph(context.Context, string, string, protocol.GraphRequest, Lease) (json.RawMessage, error)
	GraphAction(context.Context, string, board.StateAction, Lease) (board.StateActionResult, error)
}

// Server is the control plane used by scheduling and execution supervision.
// HTTP paths, headers and payload envelopes belong to Client, not its callers.
type Server interface {
	GraphServer
	Installation(context.Context) (string, error)
	DispatcherLease(context.Context, string, string, string, string) error
	Settings(context.Context) (board.Settings, error)
	List(context.Context) ([]board.Summary, error)
	Schedule(context.Context, string, ScheduleQuery) (board.SchedulePage, error)
	PendingExecutions(context.Context, string, int64) (board.ExecutionPage, error)
	Prepare(context.Context, board.Execution, Lease) (board.Execution, error)
	Execution(context.Context, string, string, string) (board.Execution, error)
	Resume(context.Context, string, string, Lease) (board.Execution, error)
	ChangeStatus(context.Context, string, string, string, protocol.Result, Lease) error
	Apply(context.Context, string, string, Lease) (string, error)
	Retry(context.Context, string, string, bool) error
	Observe(context.Context, string, string, *protocol.DecisionMetrics, Lease) error
	Claim(context.Context, string, Lease, string) error
	Renew(context.Context, string, Lease, string) error
	Release(context.Context, string, Lease) error
	OpenInput(context.Context, protocol.Job, board.InputFile) (io.ReadCloser, error)
}
