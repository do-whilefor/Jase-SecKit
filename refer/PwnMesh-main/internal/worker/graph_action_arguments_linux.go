package worker

import (
	"bytes"
	"encoding/json"
	"fmt"
	"maps"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"pwnmesh/internal/agent"
	board "pwnmesh/internal/board/model"
)

func invalidGraphArgument(field, message string) error {
	return fmt.Errorf("%s: %s", field, message)
}

// Select the discriminator branch before using the shared tool validator,
// which intentionally does not interpret oneOf. No draft or bridge is touched.
func graphActionArguments(raw json.RawMessage, schema map[string]any) (board.StateAction, string, error) {
	var action board.StateAction
	encoded, _ := json.Marshal(schema)
	if err := agent.ValidateArguments(encoded, raw); err != nil {
		return action, "", err
	}
	var input map[string]any
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	_ = decoder.Decode(&input)
	if err := requiredGraphValues(input, schema, ""); err != nil {
		return action, "", err
	}
	op := input["op"].(string)
	for _, item := range schema["oneOf"].([]any) {
		branch := item.(map[string]any)
		props := branch["properties"].(map[string]any)
		if props["op"].(map[string]any)["enum"].([]string)[0] != op {
			continue
		}
		payloadSchema := props["payload"].(map[string]any)
		if _, found := input["payload"]; !found && payloadSchema["required"] != nil {
			return action, "", invalidGraphArgument("payload", "provide an object for this operation")
		}
		payload, _ := input["payload"].(map[string]any)
		if discriminator, ok := payloadSchema["properties"].(map[string]any)["action"]; ok {
			if payload["action"] != discriminator.(map[string]any)["enum"].([]string)[0] {
				continue
			}
		}
		encoded, _ := json.Marshal(branch)
		if err := agent.ValidateArguments(encoded, raw); err != nil {
			return action, "", err
		}
		if err := requiredGraphValues(input, branch, ""); err != nil {
			return action, "", err
		}
		if err := requiredGraphValues(payload, payloadSchema, "payload."); err != nil {
			return action, "", err
		}
		if err := graphValueConstraints(input, branch, ""); err != nil {
			return action, "", err
		}
		if err := json.Unmarshal(raw, &action); err != nil {
			return action, "", invalidGraphArgument("$", err.Error())
		}
		gap, _ := input["gap_id"].(string)
		return action, gap, nil
	}
	return action, "", invalidGraphArgument("payload.action", "select an action listed for op "+op)
}

// The shared validator owns types, properties and enums. State tools also use
// bounded collections and nested alternatives; enforce those advertised
// constraints before an invalid action can reserve a draft key or reach RPC.
func graphValueConstraints(value any, schema map[string]any, path string) error {
	if alternatives, ok := schema["oneOf"].([]any); ok {
		matches := 0
		matchedFields := []string{}
		failures := []string{}
		for _, alternative := range alternatives {
			branch := maps.Clone(schema)
			delete(branch, "oneOf")
			maps.Copy(branch, alternative.(map[string]any))
			// Wrap values so the object-only shared validator can also check
			// primitive alternatives, while preserving exact JSON numbers.
			encoded, _ := json.Marshal(map[string]any{"type": "object", "properties": map[string]any{"value": branch}})
			raw, _ := json.Marshal(map[string]any{"value": value})
			err := agent.ValidateArguments(encoded, raw)
			if err == nil {
				err = graphValueConstraints(value, branch, path)
			}
			if err == nil {
				matches++
				fields, _ := alternative.(map[string]any)["required"].([]string)
				matchedFields = append(matchedFields, strings.Join(fields, ","))
			} else {
				failures = append(failures, strings.ReplaceAll(err.Error(), "arguments.value", path))
			}
		}
		if matches != 1 {
			if matches > 1 {
				return invalidGraphArgument(path, "choose only one selector: "+strings.Join(matchedFields, " or "))
			}
			return invalidGraphArgument(path, "provide exactly one supported shape; "+strings.Join(failures, "; "))
		}
		return nil
	}
	switch input := value.(type) {
	case map[string]any:
		properties, _ := schema["properties"].(map[string]any)
		for name, property := range properties {
			if entry, exists := input[name]; exists {
				field := name
				if path != "" {
					field = path + "." + name
				}
				// Only declared state fields reach this check. Opaque repair
				// values may contain arbitrary keys and retain their own policy.
				if text, ok := entry.(string); ok {
					if maximum := board.StateTextMaxBytes(name); maximum > 0 && len(text) > maximum {
						return invalidGraphArgument(field, fmt.Sprintf("provide at most %d UTF-8 bytes", maximum))
					}
				}
				if err := graphValueConstraints(entry, property.(map[string]any), field); err != nil {
					return err
				}
			}
		}
	case []any:
		if minimum, ok := schema["minItems"].(int); ok && len(input) < minimum {
			return invalidGraphArgument(path, fmt.Sprintf("provide at least %d item(s)", minimum))
		}
		if maximum, ok := schema["maxItems"].(int); ok && len(input) > maximum {
			return invalidGraphArgument(path, fmt.Sprintf("provide at most %d item(s)", maximum))
		}
		seen := map[string]bool{}
		for n, entry := range input {
			field := fmt.Sprintf("%s[%d]", path, n)
			if schema["uniqueItems"] == true {
				encoded, _ := json.Marshal(entry)
				if seen[string(encoded)] {
					return invalidGraphArgument(field, "remove the duplicate item")
				}
				seen[string(encoded)] = true
			}
			if item, ok := schema["items"].(map[string]any); ok {
				if err := graphValueConstraints(entry, item, field); err != nil {
					return err
				}
			}
		}
	case string:
		length := utf8.RuneCountInString(input)
		if minimum, ok := schema["minLength"].(int); ok && length < minimum {
			return invalidGraphArgument(path, fmt.Sprintf("provide at least %d character(s)", minimum))
		}
		if maximum, ok := schema["maxLength"].(int); ok && length > maximum {
			return invalidGraphArgument(path, fmt.Sprintf("provide at most %d character(s)", maximum))
		}
		if pattern, ok := schema["pattern"].(string); ok {
			if pattern == `\S` && strings.TrimSpace(input) == "" {
				return invalidGraphArgument(path, "provide a nonempty value")
			}
			if matched, _ := regexp.MatchString(pattern, input); !matched {
				return invalidGraphArgument(path, "match pattern "+pattern)
			}
		}
		if schema["format"] == "date-time" {
			if _, err := time.Parse(time.RFC3339, input); err != nil {
				return invalidGraphArgument(path, "provide an RFC3339 timestamp with a timezone")
			}
		}
	}
	return nil
}

// Missing fields and types are handled by agent.ValidateArguments. Preserve
// the existing nonempty draft contract with errors naming the repairable field.
func requiredGraphValues(input map[string]any, schema map[string]any, prefix string) error {
	required, _ := schema["required"].([]string)
	for _, name := range required {
		if text, ok := input[name].(string); ok && strings.TrimSpace(text) == "" {
			return invalidGraphArgument(prefix+name, "provide a nonempty value")
		}
	}
	return nil
}
