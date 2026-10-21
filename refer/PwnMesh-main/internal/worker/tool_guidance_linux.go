//go:build linux

package worker

import (
	"slices"
	"strings"

	"pwnmesh/internal/agent"
)

const toolGuidancePrefix = "Guidance for currently available tools:\n"

// Capability guidance is a replaceable request projection, not part of the
// pinned assignment. Phase changes can remove it without rewriting history.
func pinToolGuidance(loop *agent.Loop) {
	if !slices.Contains(loop.ContextDataPrefixes, toolGuidancePrefix) {
		loop.ContextDataPrefixes = append(loop.ContextDataPrefixes, toolGuidancePrefix)
	}
	data := make([]string, 0, len(loop.ContextData)+1)
	for _, item := range loop.ContextData {
		if !strings.HasPrefix(item, toolGuidancePrefix) {
			data = append(data, item)
		}
	}
	if loop.ToolsDisabledReason == "" {
		seen := make(map[string]bool)
		var rules []string
		for _, tool := range loop.Tools {
			for _, text := range tool.PromptGuidelines {
				rule := strings.TrimSpace(text)
				if rule != "" && !seen[rule] {
					seen[rule] = true
					rules = append(rules, "- "+rule)
				}
			}
		}
		if len(rules) != 0 {
			data = append(data, toolGuidancePrefix+strings.Join(rules, "\n"))
		}
	}
	loop.ContextData = data
}
