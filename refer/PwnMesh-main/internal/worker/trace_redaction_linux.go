//go:build linux

package worker

import (
	"encoding/json"
	"io"
	"regexp"
	"strings"
)

const traceCredentialName = `(?:authorization|proxy-authorization|cookie|set-cookie|[a-z0-9_]*(?:password|passwd|api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret)[a-z0-9_]*)`

var traceCredentialKey = regexp.MustCompile(`(?i)^` + traceCredentialName + `$`)
var traceCredentialFields = regexp.MustCompile(`(?im)(["']?` + traceCredentialName + `["']?\s*[:=]\s*)(?:"(?:\\[^\r\n]|[^"\\\r\n])*"|'(?:\\[^\r\n]|[^'\\\r\n])*'|[^\r\n,}]+)`)
var traceBearer = regexp.MustCompile(`(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*`)
var traceAPIKey = regexp.MustCompile(`\bsk-[A-Za-z0-9_-]{12,}\b`)
var traceURLCredentials = regexp.MustCompile(`(?i)(https?://)[^/\s:@]+:[^/\s@]+@`)

// This removes recognizable credential fields and token formats. The source
// journal is untouched; the response explicitly marks this as a projection.
func redactTraceCredentials(text string) string {
	// Preserve structured tool receipts. Replacing raw JSON tokens can remove
	// quotes and hide all outcome/context fields from downstream projections.
	decoder := json.NewDecoder(strings.NewReader(text))
	decoder.UseNumber()
	var value any
	if decoder.Decode(&value) == nil && decoder.Decode(new(any)) == io.EOF {
		if filtered, changed := redactTraceJSON(value); changed {
			if raw, err := json.Marshal(filtered); err == nil {
				return string(raw)
			}
		}
		return text
	}
	return redactTraceText(text)
}

func redactTraceJSON(value any) (any, bool) {
	changed := false
	switch item := value.(type) {
	case map[string]any:
		for key, field := range item {
			if traceCredentialKey.MatchString(key) {
				if field != "[redacted]" {
					item[key], changed = "[redacted]", true
				}
				continue
			}
			filtered, redacted := redactTraceJSON(field)
			item[key], changed = filtered, changed || redacted
		}
	case []any:
		for index, field := range item {
			filtered, redacted := redactTraceJSON(field)
			item[index], changed = filtered, changed || redacted
		}
	case string:
		filtered := redactTraceText(item)
		return filtered, filtered != item
	}
	return value, changed
}

func redactTraceText(text string) string {
	text = traceCredentialFields.ReplaceAllString(text, "${1}[redacted]")
	text = traceBearer.ReplaceAllString(text, "Bearer [redacted]")
	text = traceAPIKey.ReplaceAllString(text, "[redacted]")
	return traceURLCredentials.ReplaceAllString(text, "${1}[redacted]@")
}
