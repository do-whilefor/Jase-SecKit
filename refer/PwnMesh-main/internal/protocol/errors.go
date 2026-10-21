package protocol

import (
	"errors"

	"pwnmesh/internal/board/model"
)

// RPCError retains machine-readable failure identity across HTTP and the
// container bridge. Detail is display text and never controls new recovery.
type RPCError struct {
	Code   string `json:"code"`
	Status int    `json:"status,omitempty"`
	Detail string `json:"detail"`
}

func (e *RPCError) Error() string { return e.Detail }

const CodeRequestFailed = "request_failed"

func GraphFailure(err error) *RPCError {
	var failure *RPCError
	if errors.As(err, &failure) {
		copy := *failure
		copy.Detail = err.Error()
		if copy.Code == "" {
			copy.Code = CodeRequestFailed
		}
		return &copy
	}
	var api *model.APIError
	if errors.As(err, &api) {
		code := api.Code
		if code == "" {
			code = CodeRequestFailed
		}
		return &RPCError{Code: code, Status: api.Status, Detail: api.Error()}
	}
	return &RPCError{Code: CodeRequestFailed, Detail: err.Error()}
}
