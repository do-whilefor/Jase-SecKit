package launchbridge

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"
)

func ContainsCredential(value string, secrets ...string) bool {
	for _, secret := range secrets {
		if secret != "" && strings.Contains(value, secret) {
			return true
		}
	}
	return false
}

// Inspect decoded strings at every JSON depth, including object keys and raw
// tool arguments. Token scanning also checks duplicate keys that unmarshaling
// into a map would discard. Invalid JSON fails closed.
func JSONContainsCredential(raw []byte, secrets ...string) bool {
	if !json.Valid(raw) {
		return true
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	for {
		token, err := decoder.Token()
		if err == io.EOF {
			return false
		}
		if err != nil {
			return true
		}
		if value, ok := token.(string); ok && ContainsCredential(value, secrets...) {
			return true
		}
	}
}
