package provider

import (
	"net/url"
	"strings"
)

const DefaultBaseURL = "https://api.deepseek.com/anthropic"
const DefaultOpenAIBaseURL = "https://api.openai.com/v1"

// Endpoint resolves the request URL once for settings, authentication,
// transport and model identity.
func Endpoint(protocol, baseURL string) string {
	base := strings.TrimRight(baseURL, "/")
	if protocol == "openai" {
		if base == "" {
			base = DefaultOpenAIBaseURL
		}
		if strings.HasSuffix(base, "/chat/completions") {
			return base
		}
		if parsed, err := url.Parse(base); err == nil && parsed.Path != "" {
			return base + "/chat/completions"
		}
		return base + "/v1/chat/completions"
	}
	if base == "" {
		base = DefaultBaseURL
	}
	if strings.HasSuffix(base, "/messages") {
		return base
	}
	if strings.HasSuffix(base, "/v1") {
		return base + "/messages"
	}
	return base + "/v1/messages"
}
