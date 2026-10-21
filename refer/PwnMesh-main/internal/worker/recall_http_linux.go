//go:build linux

package worker

import (
	"encoding/json"

	"pwnmesh/internal/board/model"
)

// These are historical tool receipts, not a fresh applicability verdict. The
// durable receipt retains full context and evidence hashes outside this index.
type recallHTTPResult struct {
	Index          int                      `json:"index,omitempty"`
	Request        *recallHTTPRequest       `json:"request,omitempty"`
	Status         *int                     `json:"status"`
	Complete       *bool                    `json:"complete"`
	BodyBytes      *int64                   `json:"body_bytes,omitempty"`
	ObservedAt     string                   `json:"observed_at,omitempty"`
	Context        model.ObservationContext `json:"context,omitempty"`
	ContextMissing []string                 `json:"context_missing,omitempty"`
	ContextSource  string                   `json:"context_source,omitempty"`
	Error          string                   `json:"error,omitempty"`
}

type recallHTTPRequest struct {
	Method    string `json:"method"`
	URL       string `json:"url"`
	Truncated bool   `json:"truncated,omitempty"`
}

func recallHTTP(content string) (summary *recallHTTPResult, path, hash, preview string, truncated bool) {
	var receipt struct {
		recallHTTPResult
		Message string `json:"message"`
		Receipt struct {
			Path   string `json:"path"`
			SHA256 string `json:"sha256"`
		} `json:"receipt"`
	}
	if json.Unmarshal([]byte(content), &receipt) != nil {
		preview, truncated = traceExcerpt(content, 160)
		return
	}
	summary = &receipt.recallHTTPResult
	clip := func(value string, size int) string {
		bounded, omitted := traceExcerpt(value, size)
		truncated = truncated || omitted
		return bounded
	}
	summary.ObservedAt = clip(summary.ObservedAt, 64)
	summary.Error = clip(summary.Error, 96)
	if summary.Request != nil {
		var methodClipped, urlClipped bool
		summary.Request.Method, methodClipped = traceExcerpt(summary.Request.Method, 64)
		summary.Request.URL, urlClipped = traceExcerpt(summary.Request.URL, 256)
		summary.Request.Truncated = summary.Request.Truncated || methodClipped || urlClipped
		truncated = truncated || summary.Request.Truncated
	}
	preview = clip(receipt.Message, 160)
	labels := model.ObservationContext{}
	summary.ContextMissing = summary.Context.Missing()
	for _, key := range model.ObservationContextFields() {
		if value := summary.Context[key]; value != "" {
			labels[key] = clip(value, 128)
		}
	}
	summary.Context = labels
	// These optional labels are supplied by the caller, never verified by the
	// HTTP status or evidence checksum. Missing labels remain explicitly unknown.
	summary.ContextSource = "caller"
	path, hash = receipt.Receipt.Path, receipt.Receipt.SHA256
	if len(path) > 512 {
		path, hash, truncated = "", "", true
	}
	return
}
