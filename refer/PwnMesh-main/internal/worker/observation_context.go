package worker

import "pwnmesh/internal/board/model"

func observationContextSchema() map[string]any {
	properties := map[string]any{}
	for _, field := range model.ObservationContextFields() {
		properties[field] = map[string]any{"type": "string", "minLength": 1,
			"maxLength": model.ObservationContextMaxChars, "pattern": `\S`}
	}
	return map[string]any{"type": "object", "properties": properties, "additionalProperties": false,
		"description": "Optional caller-supplied applicability labels, never credentials or verified identity. Omit unknown conditions; derived facts do not inherit them."}
}
