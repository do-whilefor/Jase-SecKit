package provider

import (
	"crypto/sha256"
	"encoding/hex"
	"net/url"
	"strings"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelwire"
)

func (p *Client) ModelDescriptor() agent.ModelDescriptor {
	api := "anthropic-messages"
	if p.Protocol == "openai" {
		api = "openai-completions"
	}
	id := p.Model
	if id == "" {
		id = modelwire.DefaultModel
	}
	limit := p.MaxTokens
	if limit <= 0 {
		limit = modelwire.DefaultMaxTokens
	}
	// Bind replay to the configured endpoint, without transmitting URLs or
	// guessing the vendor behind a compatible gateway. Authentication is excluded.
	endpoint, _ := url.Parse(Endpoint(p.Protocol, p.BaseURL))
	identity := ""
	if endpoint != nil {
		identity = strings.ToLower(endpoint.Scheme) + "://" + strings.ToLower(endpoint.Host) + endpoint.EscapedPath()
	}
	digest := sha256.Sum256([]byte(identity))
	return agent.ModelDescriptor{ID: id, API: api, Provider: "endpoint:" + hex.EncodeToString(digest[:]),
		Reasoning: p.Protocol != "openai" || p.ReasoningEffort != "" || p.ReasoningContent,
		MaxTokens: limit, Input: []string{"text"}}
}
