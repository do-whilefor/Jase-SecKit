//go:build linux

package tools

import (
	"encoding/json"
	"os/exec"

	"pwnmesh/internal/agent"
)

type outputDetails struct {
	Truncated             bool   `json:"truncated"`
	TruncatedBy           string `json:"truncatedBy,omitempty"`
	FullOutputPath        string `json:"fullOutputPath,omitempty"`
	SourcePath            string `json:"sourcePath,omitempty"`
	Complete              bool   `json:"complete"`
	OutputBytes           int    `json:"outputBytes"`
	TotalBytes            int64  `json:"totalBytes"`
	OutputLines           int    `json:"outputLines,omitempty"`
	NextOffset            int    `json:"nextOffset,omitempty"`
	FirstLineExceedsLimit bool   `json:"firstLineExceedsLimit,omitempty"`
}

func resultWithDetails(text string, details any) agent.ToolResult {
	encoded, _ := json.Marshal(details)
	return agent.ToolResult{Text: text, Details: encoded}
}

// A nonzero exit status does not by itself mean captured output is incomplete.
func outputIsComplete(err error) bool {
	if err == nil {
		return true
	}
	switch failure := err.(type) {
	case *exec.ExitError:
		return true
	case interface{ Unwrap() []error }:
		for _, cause := range failure.Unwrap() {
			if !outputIsComplete(cause) {
				return false
			}
		}
		return true
	case interface{ Unwrap() error }:
		return outputIsComplete(failure.Unwrap())
	default:
		return false
	}
}
