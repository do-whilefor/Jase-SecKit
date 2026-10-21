//go:build linux

package worker

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/board/model"
	"pwnmesh/internal/process"
)

type httpReplayInput struct {
	Input         string                   `json:"input"`
	Index         int                      `json:"index"`
	BaseURL       string                   `json:"base_url,omitempty"`
	Headers       string                   `json:"headers,omitempty"`
	RemoveHeaders []string                 `json:"remove_headers,omitempty"`
	Timeout       int                      `json:"timeout,omitempty"`
	Context       model.ObservationContext `json:"context,omitempty"`
}

// Replay owns a private evidence directory and the usual Worker process group.
// It never automatically retries a request, including after partial responses.
func httpReplayTool(j Job, o Options) agent.Tool {
	definition := agent.Definition{
		Name:        "http_replay",
		Description: `Replay one selected HAR/raw HTTP request with pwn-http. Inspect captures with pwn-http inspect first. Returns HTTP status, completeness and hashed evidence paths; incomplete responses remain usable only as partial observations. Direct transport ignores proxy environment variables. No redirects or retries. Context labels are caller assertions, never credentials; omit unknown labels.`,
		Schema:      httpReplaySchema(),
	}
	return agent.Tool{Definition: definition, Execute: agent.TextExecutor(func(parent context.Context, raw json.RawMessage) (string, error) {
		if err := parent.Err(); err != nil {
			return "", err
		}
		if err := agent.ValidateArguments(definition.Schema, raw); err != nil {
			return "", err
		}
		var input httpReplayInput
		if err := json.Unmarshal(raw, &input); err != nil {
			return "", err
		}
		if err := input.Context.Validate(); err != nil {
			return "", err
		}
		command, err := exec.LookPath("pwn-http")
		if err != nil {
			return "", errors.New("pwn-http is unavailable in this runtime")
		}
		if input.Timeout == 0 {
			input.Timeout = 30
		}
		if o.RunDir == "" || j.Workspace == "" {
			return "", errors.New("HTTP replay requires a run directory and workspace")
		}
		if err := os.MkdirAll(o.RunDir, 0700); err != nil {
			return "", err
		}
		dir, err := os.MkdirTemp(o.RunDir, "http-")
		if err != nil {
			return "", err
		}
		dir, err = filepath.Abs(dir)
		if err != nil {
			return "", err
		}
		output := filepath.Join(dir, "evidence")
		path := func(value string) string {
			if filepath.IsAbs(value) {
				return value
			}
			return filepath.Join(j.Workspace, value)
		}
		args := []string{"replay", path(input.Input), "--index", strconv.Itoa(input.Index), "--output", output, "--timeout", strconv.Itoa(input.Timeout)}
		if input.BaseURL != "" {
			args = append(args, "--base-url", input.BaseURL)
		}
		if input.Headers != "" {
			args = append(args, "--headers", path(input.Headers))
		}
		for _, name := range input.RemoveHeaders {
			args = append(args, "--remove-header", name)
		}
		if input.Context != nil {
			encoded, _ := json.Marshal(input.Context)
			contextPath := filepath.Join(dir, "context.json")
			if err := os.WriteFile(contextPath, encoded, 0600); err != nil {
				return "", err
			}
			args = append(args, "--context", contextPath)
		}
		stdout, err := os.OpenFile(filepath.Join(dir, "receipt.json"), os.O_CREATE|os.O_EXCL|os.O_RDWR, 0600)
		if err != nil {
			return "", err
		}
		defer stdout.Close()
		stderr, err := os.OpenFile(filepath.Join(dir, "stderr.txt"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			return "", err
		}
		defer stderr.Close()
		started := time.Now().UTC()
		ctx, cancel := context.WithTimeout(parent, time.Duration(input.Timeout+1)*time.Second)
		defer cancel()
		runErr := process.RunStreams(ctx, j.Workspace, o.RunDir, stdout, stderr, command, args...)
		if _, err := stdout.Seek(0, io.SeekStart); err != nil {
			return "", err
		}
		data, err := io.ReadAll(io.LimitReader(stdout, (64<<10)+1))
		if err != nil {
			return "", err
		}
		var result map[string]any
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.UseNumber()
		decodeErr := decoder.Decode(&result)
		complete, valid := result["complete"].(bool)
		retained := retainedHTTPReferences(output)
		if decodeErr != nil || !valid || len(data) > 64<<10 || decoder.Decode(new(any)) != io.EOF || !validHTTPReceipt(result, output, retained) {
			// A deadline/process interruption may stop Python before its JSON is
			// printed. Keep a conservative receipt and every existing file.
			result = map[string]any{"status": nil, "complete": false, "error": "replay_interrupted",
				"message":     "No complete replay receipt; inspect retained evidence before retrying",
				"observed_at": nil, "started_at": started.Format(time.RFC3339Nano)}
			result["context"], result["context_missing"], result["context_source"] = input.Context, input.Context.Missing(), "caller"
			complete = false
		}
		result["evidence"] = retained
		if runErr != nil {
			result["complete"], complete = false, false
			if _, ok := result["error"]; !ok {
				result["error"] = "replay_process_failed"
			}
		}
		result["run_id"], result["output"], result["index"] = j.RunID, output, input.Index
		result["transport"], result["proxy_environment_used"] = "direct", false
		encoded, err := json.Marshal(result)
		if err != nil {
			return "", err
		}
		if err := stdout.Truncate(0); err != nil {
			return "", err
		}
		if _, err := stdout.Seek(0, io.SeekStart); err != nil {
			return "", err
		}
		if _, err := stdout.Write(encoded); err != nil {
			return "", err
		}
		digest := sha256.Sum256(encoded)
		result["receipt"] = map[string]any{"path": stdout.Name(), "sha256": hex.EncodeToString(digest[:]), "bytes": len(encoded)}
		encoded, err = json.Marshal(result)
		if err != nil {
			return "", err
		}
		if !complete {
			// Loop preserves this as one valid JSON string with is_error=true.
			return "", errors.New(string(encoded))
		}
		return string(encoded), nil
	})}
}

func httpReplaySchema() json.RawMessage {
	raw, _ := json.Marshal(map[string]any{
		"type": "object", "properties": map[string]any{
			"input":          map[string]any{"type": "string", "minLength": 1},
			"index":          map[string]any{"type": "integer", "minimum": 1},
			"base_url":       map[string]any{"type": "string", "description": "Explicit http(s) origin for origin-form raw requests."},
			"headers":        map[string]any{"type": "string", "description": "Path to JSON header overrides; null values remove headers."},
			"remove_headers": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
			"timeout":        map[string]any{"type": "integer", "minimum": 1, "maximum": 120},
			"context":        observationContextSchema(),
		}, "required": []string{"input", "index"}, "additionalProperties": false,
	})
	return raw
}
