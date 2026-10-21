package model

import (
	"bytes"
	"encoding/json"
	"slices"
	"strings"
	"unicode/utf8"
)

const ObservationContextMaxChars = 256

// ObservationContext records caller-supplied applicability labels, never verified
// identity or credentials. Missing labels remain unknown, including on derived Facts.
type ObservationContext map[string]string

func ObservationContextFields() []string {
	return []string{"identity", "session", "target_version", "configuration"}
}

func (c ObservationContext) Validate() error {
	fields := ObservationContextFields()
	keys := make([]string, 0, len(c))
	for key := range c {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	for _, key := range keys {
		if !slices.Contains(fields, key) {
			return Err(422, "context."+key+" is not a supported observation condition")
		}
		if strings.TrimSpace(c[key]) == "" || utf8.RuneCountInString(c[key]) > ObservationContextMaxChars {
			return Err(422, "context."+key+" must be a nonblank label of at most 256 characters")
		}
	}
	return nil
}

func (c ObservationContext) Missing() []string {
	missing := []string{}
	for _, field := range ObservationContextFields() {
		if strings.TrimSpace(c[field]) == "" {
			missing = append(missing, field)
		}
	}
	return missing
}

// ParseObservationContext preserves absent historical fields and rejects invalid
// labels before a publication allocates an identity or saves a receipt.
func ParseObservationContext(raw json.RawMessage) (ObservationContext, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var labels map[string]json.RawMessage
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) || json.Unmarshal(raw, &labels) != nil {
		return nil, Err(422, "context must be an object of observation condition labels")
	}
	context := ObservationContext{}
	for key, rawValue := range labels {
		var value string
		if bytes.Equal(bytes.TrimSpace(rawValue), []byte("null")) || json.Unmarshal(rawValue, &value) != nil {
			return nil, Err(422, "context."+key+" must be a string label")
		}
		context[key] = value
	}
	if err := context.Validate(); err != nil {
		return nil, err
	}
	return context, nil
}
