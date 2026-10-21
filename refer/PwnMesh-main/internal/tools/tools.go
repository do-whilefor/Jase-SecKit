//go:build linux

// Package tools provides PwnMesh file and shell tools.
package tools

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/process"
)

const maxOutputFileBytes = 64 << 20

var errOutputLimit = errors.New("tool output exceeds 64 MiB; retained prefix is incomplete")

type Set struct {
	Dir    string
	RunDir string
	// ProcessDir binds child processes to the owning Worker launch. Output
	// files remain private to RunDir; an empty value uses RunDir for both.
	ProcessDir  string
	Env         []string
	OutputBytes int
	ToolTimeout time.Duration
}

func (s *Set) All() []agent.Tool {
	def := func(name, desc, schema string, fn func(context.Context, json.RawMessage) (agent.ToolResult, error), guidelines ...string) agent.Tool {
		return agent.Tool{Definition: agent.Definition{Name: name, Description: desc, Schema: json.RawMessage(schema)}, Execute: fn, PromptGuidelines: guidelines}
	}
	return []agent.Tool{
		def("read", "Read a text file with optional 1-based offset and line limit (default 2000). Truncated reads return the exact next offset.", `{"type":"object","properties":{"path":{"type":"string"},"offset":{"type":"integer","minimum":1},"limit":{"type":"integer","minimum":1}},"required":["path"],"additionalProperties":false}`, s.readResult,
			"Continue truncated reads at the reported offset."),
		def("bash", "Run a bash command in the current working directory. Long output is saved to a file; output above 64 MiB stops the command and retains a partial log.", `{"type":"object","properties":{"command":{"type":"string"},"timeout":{"type":"integer","minimum":1,"description":"Seconds; default 120. Capped by the runtime ceiling (default 120 seconds) and remaining task time."}},"required":["command"],"additionalProperties":false}`, s.bashResult,
			"Run complete commands; check options and producer/consumer formats. Save reusable scripts and invoke them by path."),
		def("edit", "Apply exact replacements in one UTF-8 file. Supply an edits array; all matches refer to the original file and must not overlap.", fmt.Sprintf(`{"type":"object","properties":{"path":{"type":"string"},"edits":{"type":"array","minItems":1,"maxItems":%d,"items":{"type":"object","properties":{"oldText":{"type":"string","minLength":1},"newText":{"type":"string"}},"required":["oldText","newText"],"additionalProperties":false}}},"required":["path","edits"],"additionalProperties":false}`, maxEditReplacements), s.editResult,
			"Reuse retained scripts after recovery; batch disjoint edits against the original file."),
		def("write", `Write a file.

- Use exactly one of content (generated text) or source_path (byte-exact copy).
- Optional source_start_line/source_end_line must be paired, 1-based inclusive.
- source_sha256 verifies the entire source file before copying.
- Creates parent directories; returns byte count and SHA-256.`, `{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"source_path":{"type":"string"},"source_start_line":{"type":"integer","minimum":1},"source_end_line":{"type":"integer","minimum":1},"source_sha256":{"type":"string"}},"required":["path"],"additionalProperties":false}`, agent.TextExecutor(s.write),
			"Copy existing scripts with source_path instead of regenerating them."),
		def("grep", "Search file contents with ripgrep; regex by default.", `{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"glob":{"type":"string"},"ignoreCase":{"type":"boolean"},"literal":{"type":"boolean"}},"required":["pattern"],"additionalProperties":false}`, s.grep),
		def("find", "Find file paths matching a glob, including hidden files.", `{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"],"additionalProperties":false}`, s.find),
		def("ls", "List entries in a directory.", `{"type":"object","properties":{"path":{"type":"string"}},"additionalProperties":false}`, s.ls),
	}
}
func decode(raw json.RawMessage, dst any, required ...string) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return err
	}
	if fields == nil {
		return errors.New("arguments must be an object")
	}
	for k, v := range fields {
		if string(v) == "null" {
			return fmt.Errorf("argument %s cannot be null", k)
		}
	}
	for _, k := range required {
		v, ok := fields[k]
		if !ok || string(v) == "null" {
			return fmt.Errorf("missing argument %s", k)
		}
	}
	d := json.NewDecoder(strings.NewReader(string(raw)))
	d.DisallowUnknownFields()
	return d.Decode(dst)
}
func (s *Set) path(path string) string {
	if path == "" {
		return s.Dir
	}
	if filepath.IsAbs(path) {
		return filepath.Clean(path)
	}
	return filepath.Join(s.Dir, path)
}
func (s *Set) limit() int {
	if s.OutputBytes > 0 {
		return s.OutputBytes
	}
	return 32000
}
func (s *Set) outputResult(ctx context.Context, f *os.File, err error) (agent.ToolResult, error) {
	details := outputDetails{Complete: outputIsComplete(err)}
	if info, statErr := f.Stat(); statErr == nil {
		details.TotalBytes = info.Size()
	}
	if _, seekErr := f.Seek(0, 0); seekErr != nil {
		return agent.ToolResult{}, errors.Join(err, seekErr)
	}
	data, readErr := io.ReadAll(io.LimitReader(f, int64(s.limit()+1)))
	text := string(data)
	if len(data) > s.limit() {
		details.Truncated = true
		details.TruncatedBy = "bytes"
		head := s.limit() / 2
		tailBytes := s.limit() - head
		if _, seekErr := f.Seek(-int64(tailBytes), io.SeekEnd); seekErr != nil {
			return agent.ToolResult{}, errors.Join(err, readErr, seekErr)
		}
		tail, tailErr := io.ReadAll(io.LimitReader(f, int64(tailBytes)))
		readErr = errors.Join(readErr, tailErr)
		// Omit complete runes at the clipping boundaries instead of turning
		// otherwise valid UTF-8 into replacement characters in the preview.
		for head > 0 && !utf8.RuneStart(data[head]) {
			head--
		}
		start := 0
		for start < len(tail) && !utf8.RuneStart(tail[start]) {
			start++
		}
		label := "Full output: "
		if !details.Complete {
			label = "Partial output: "
		}
		// Capture may have reached its timeout; retain already captured bounded
		// bytes without treating that cancellation as a failed hash operation.
		retained, retainErr := retainOutput(context.WithoutCancel(ctx), f)
		readErr = errors.Join(readErr, retainErr)
		details.FullOutputPath = retained
		details.OutputBytes = head + len(tail) - start
		text = string(data[:head]) + "\n[Middle omitted. " + label + retained + "]\n" + string(tail[start:])
	} else {
		details.OutputBytes = len(data)
	}
	if errors.Is(err, errOutputLimit) {
		details.Truncated = true
		details.TruncatedBy = "capture_limit"
	}
	details.Complete = details.Complete && readErr == nil
	if !details.Complete {
		text += "\n[Captured output may be incomplete.]"
	}
	return resultWithDetails(strings.ToValidUTF8(text, "�"), details), errors.Join(err, readErr)
}
func (s *Set) runResult(ctx context.Context, timeout time.Duration, name string, args ...string) (agent.ToolResult, error) {
	ceiling := s.ToolTimeout
	if ceiling <= 0 {
		ceiling = 2 * time.Minute
	}
	if timeout <= 0 || timeout > ceiling {
		timeout = ceiling
	}
	if err := os.MkdirAll(s.RunDir, 0700); err != nil {
		return agent.ToolResult{}, err
	}
	f, err := os.CreateTemp(s.RunDir, "output-*.txt")
	if err != nil {
		return agent.ToolResult{}, err
	}
	defer f.Close()
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	processDir := s.ProcessDir
	if processDir == "" {
		processDir = s.RunDir
	}
	if len(s.Env) != 0 {
		args = append(append(append([]string{}, s.Env...), name), args...)
		name = "env"
	}
	// Cap the captured streams, not every file the command may legitimately
	// build or download. Both streams share this pipe and one retained limit.
	reader, writer, err := os.Pipe()
	if err != nil {
		return agent.ToolResult{}, err
	}
	// A background process may clear its ownership token yet retain stdout.
	// Its open descriptor must not keep capture waiting past the tool deadline.
	stopCapture := context.AfterFunc(ctx, func() { reader.Close() })
	defer stopCapture()
	captured := make(chan error, 1)
	go func() {
		_, copyErr := io.Copy(&outputLimitWriter{writer: f, remaining: maxOutputFileBytes}, reader)
		if copyErr != nil {
			cancel()
		}
		reader.Close()
		captured <- copyErr
	}()
	err = process.Run(ctx, s.Dir, processDir, writer, name, args...)
	closeErr := writer.Close()
	captureErr := <-captured
	return s.outputResult(ctx, f, errors.Join(err, ctx.Err(), closeErr, captureErr))
}

type outputLimitWriter struct {
	writer    io.Writer
	remaining int
}

func (w *outputLimitWriter) Write(data []byte) (int, error) {
	overflow := len(data) > w.remaining
	if overflow {
		data = data[:w.remaining]
	}
	n, err := w.writer.Write(data)
	w.remaining -= n
	if err == nil && overflow {
		err = errOutputLimit
	}
	return n, err
}

func (s *Set) capture(ctx context.Context, write func(io.Writer) error) (agent.ToolResult, error) {
	if err := ctx.Err(); err != nil {
		return agent.ToolResult{}, err
	}
	if err := os.MkdirAll(s.RunDir, 0700); err != nil {
		return agent.ToolResult{}, err
	}
	f, err := os.CreateTemp(s.RunDir, "output-*.txt")
	if err != nil {
		return agent.ToolResult{}, err
	}
	defer f.Close()
	err = write(&outputLimitWriter{writer: f, remaining: maxOutputFileBytes})
	return s.outputResult(ctx, f, err)
}

func (s *Set) bashResult(ctx context.Context, raw json.RawMessage) (agent.ToolResult, error) {
	var a struct {
		Command string `json:"command"`
		Timeout int    `json:"timeout"`
	}
	if err := decode(raw, &a, "command"); err != nil {
		return agent.ToolResult{}, err
	}
	if strings.TrimSpace(a.Command) == "" {
		return agent.ToolResult{}, errors.New("command must not be empty")
	}
	if a.Timeout < 0 {
		return agent.ToolResult{}, errors.New("timeout must be positive")
	}
	if a.Timeout == 0 {
		a.Timeout = 120
	}
	if a.Timeout > 86400 {
		return agent.ToolResult{}, errors.New("timeout must not exceed 86400 seconds")
	}
	return s.runResult(ctx, time.Duration(a.Timeout)*time.Second, "bash", "-lc", a.Command)
}

// Nonblocking open followed by fstat avoids hanging on FIFOs/devices, including
// symlinks that resolve to them. Reads and edits are text-file operations.
func openRegular(path string) (*os.File, error) {
	f, err := os.OpenFile(path, os.O_RDONLY|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, err
	}
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() {
		f.Close()
		if err != nil {
			return nil, err
		}
		return nil, errors.New("path must be a regular file")
	}
	return f, nil
}
func writeRegular(path string, data []byte, mode os.FileMode) error {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|syscall.O_NONBLOCK, mode)
	if err != nil {
		return err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return errors.New("path must be a regular file")
	}
	if err = f.Truncate(0); err != nil {
		return err
	}
	_, err = f.Write(data)
	return err
}
func (s *Set) grep(ctx context.Context, raw json.RawMessage) (agent.ToolResult, error) {
	var a struct {
		Pattern string `json:"pattern"`
		Path    string `json:"path"`
		Glob    string `json:"glob"`
		Ignore  bool   `json:"ignoreCase"`
		Literal bool   `json:"literal"`
	}
	if err := decode(raw, &a, "pattern"); err != nil {
		return agent.ToolResult{}, err
	}
	args := []string{"--line-number", "--hidden", "--color", "never"}
	if a.Glob != "" {
		args = append(args, "--glob", a.Glob)
	}
	if a.Ignore {
		args = append(args, "-i")
	}
	if a.Literal {
		args = append(args, "-F")
	}
	args = append(args, "--", a.Pattern, s.path(a.Path))
	out, err := s.runResult(ctx, 30*time.Second, "rg", args...)
	if out.Text == "" && onlyNoMatchExit(err) {
		out.Text, err = "No matches", nil
	}
	return out, err
}
func (s *Set) find(ctx context.Context, raw json.RawMessage) (agent.ToolResult, error) {
	var a struct {
		Pattern string `json:"pattern"`
		Path    string `json:"path"`
	}
	if err := decode(raw, &a, "pattern"); err != nil {
		return agent.ToolResult{}, err
	}
	out, err := s.runResult(ctx, 30*time.Second, "rg", "--files", "--hidden", "--glob", a.Pattern, "--", s.path(a.Path))
	if out.Text == "" && onlyNoMatchExit(err) {
		out.Text, err = "No matches", nil
	}
	return out, err
}

// Process, capture and file errors may be joined with ripgrep's exit status.
// Normalize no matches only when every retained cause is that expected status.
func onlyNoMatchExit(err error) bool {
	switch failure := err.(type) {
	case *exec.ExitError:
		return failure.ExitCode() == 1
	case interface{ Unwrap() []error }:
		causes := failure.Unwrap()
		if len(causes) == 0 {
			return false
		}
		for _, cause := range causes {
			if !onlyNoMatchExit(cause) {
				return false
			}
		}
		return true
	case interface{ Unwrap() error }:
		return onlyNoMatchExit(failure.Unwrap())
	default:
		return false
	}
}

func (s *Set) ls(ctx context.Context, raw json.RawMessage) (agent.ToolResult, error) {
	var a struct {
		Path string `json:"path"`
	}
	if err := decode(raw, &a); err != nil {
		return agent.ToolResult{}, err
	}
	if err := ctx.Err(); err != nil {
		return agent.ToolResult{}, err
	}
	dir, err := os.OpenFile(s.path(a.Path), os.O_RDONLY|syscall.O_NONBLOCK|syscall.O_DIRECTORY, 0)
	if err != nil {
		return agent.ToolResult{}, err
	}
	defer dir.Close()
	entries, err := dir.ReadDir(-1)
	if err != nil {
		return agent.ToolResult{}, err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
	return s.capture(ctx, func(out io.Writer) error {
		for _, e := range entries {
			if err := ctx.Err(); err != nil {
				return err
			}
			name := e.Name()
			if e.IsDir() {
				name += "/"
			}
			if _, err := io.WriteString(out, name+"\n"); err != nil {
				return err
			}
		}
		return nil
	})
}
