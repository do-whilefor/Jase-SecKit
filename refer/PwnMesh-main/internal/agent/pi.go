package agent

import (
	"bufio"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"time"
)

// Run delegates the conversation, tools and context lifecycle to the Pi source
// kernel. Go provides only transport, application hooks and atomic persistence.
func (l *Loop) Run(ctx context.Context, prompt string) (string, error) {
	if l.Provider == nil {
		return "", errors.New("missing model provider")
	}
	if l.TaskPrompt == "" {
		l.TaskPrompt = prompt
	}
	l.bridgeContext = ctx
	defer func() { l.bridgeContext = nil }()
	return l.pi(ctx, "run", prompt, nil)
}

// Restore derives the evidence projection from the authoritative Pi session.
func (l *Loop) Restore(ctx context.Context) error {
	l.ownState()
	if err := l.initCheckpoint(); err != nil {
		return err
	}
	if len(l.Checkpoint.PiSession) == 0 {
		return nil
	}
	_, err := l.pi(ctx, "inspect", "", nil)
	return err
}

// AppendInstruction commits an application instruction using SessionManager,
// including when called inside a phase hook. The running kernel receives the
// changed snapshot before its next request.
func (l *Loop) AppendInstruction(prompt string) error {
	ctx, cancel := l.editContext()
	defer cancel()
	_, err := l.pi(ctx, "edit", "", []string{prompt})
	return err
}

// RepairHistory asks Pi to settle interrupted calls without replaying effects.
func (l *Loop) RepairHistory() error {
	if len(l.History) == 0 && l.Checkpoint == nil {
		return nil
	}
	ctx, cancel := l.editContext()
	defer cancel()
	_, err := l.pi(ctx, "edit", "", nil)
	return err
}

func (l *Loop) editContext() (context.Context, context.CancelFunc) {
	if l.bridgeContext != nil {
		return context.WithCancel(l.bridgeContext)
	}
	return context.WithTimeout(context.Background(), 15*time.Second)
}

type piState struct {
	History      []Message       `json:"history"`
	TaskPrompt   string          `json:"taskPrompt"`
	Session      json.RawMessage `json:"session"`
	LastSequence uint64          `json:"lastSequence"`
}

type piFrame struct {
	piState
	Type      string          `json:"type"`
	ID        string          `json:"id"`
	Method    string          `json:"method"`
	Params    json.RawMessage `json:"params"`
	Text      string          `json:"text"`
	Error     string          `json:"error"`
	ErrorKind ErrorKind       `json:"errorKind"`
	Canceled  bool            `json:"canceled"`
	Deadline  bool            `json:"deadline"`
}

type piError struct {
	Message  string    `json:"message"`
	Kind     ErrorKind `json:"kind,omitempty"`
	Canceled bool      `json:"canceled,omitempty"`
	Deadline bool      `json:"deadline,omitempty"`
}

func encodePiError(err error) *piError {
	if err == nil {
		return nil
	}
	result := &piError{Message: err.Error(), Canceled: errors.Is(err, context.Canceled), Deadline: errors.Is(err, context.DeadlineExceeded)}
	var model *ModelError
	if errors.As(err, &model) {
		result.Kind = model.Kind
	}
	return result
}

func (l *Loop) config() map[string]any {
	config := map[string]any{
		"tools": l.definitions(), "toolsDisabledReason": l.ToolsDisabledReason,
		"taskPrompt": l.TaskPrompt, "pinnedInstructions": l.PinnedInstructions,
		"contextData": l.ContextData, "contextDataPrefixes": l.ContextDataPrefixes,
		"context": map[string]int{"bytes": l.ContextBytes, "tokens": l.ContextTokens,
			"targetTokens": l.ContextTargetTokens, "summaryMaxTokens": l.SummaryMaxTokens},
	}
	if provider, ok := l.Provider.(ModelProvider); ok {
		config["model"] = provider.ModelDescriptor()
	}
	return config
}

func (l *Loop) pi(ctx context.Context, operation, prompt string, instructions []string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	l.ownState()
	if err := l.initCheckpoint(); err != nil {
		return "", err
	}
	if l.SessionDir == "" {
		return "", errors.New("Pi requires a session directory")
	}
	if len(l.Checkpoint.PiSession) > 0 {
		if err := l.validatePiSession(l.Checkpoint.PiSession); err != nil {
			return "", err
		}
	}
	kernel, err := piKernelPath()
	if err != nil {
		return "", err
	}
	command := exec.Command("node", kernel)
	command.Env = piEnvironment(os.Environ())
	stdin, err := command.StdinPipe()
	if err != nil {
		return "", err
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		_ = stdin.Close()
		return "", err
	}
	if err := command.Start(); err != nil {
		return "", fmt.Errorf("start Pi kernel: %w", err)
	}
	defer func() {
		_ = stdin.Close()
		_ = command.Process.Kill()
		_ = command.Wait()
	}()
	encoder := json.NewEncoder(stdin)
	request := l.config()
	request["type"], request["prompt"], request["instructions"] = operation, prompt, instructions
	if l.Directory != "" {
		request["cwd"] = l.Directory
	}
	sessionPath, err := filepath.Abs(filepath.Join(l.SessionDir, "pi-session.jsonl"))
	if err != nil {
		return "", err
	}
	request["sessionPath"] = sessionPath
	request["session"] = l.Checkpoint.PiSession
	request["lastSequence"] = l.Checkpoint.LastSequence
	if err := encoder.Encode(request); err != nil {
		return "", fmt.Errorf("send Pi request: %w", err)
	}
	type received struct {
		frame piFrame
		err   error
	}
	frames := make(chan received)
	done := make(chan struct{})
	defer close(done)
	go func() {
		scanner := bufio.NewScanner(stdout)
		scanner.Buffer(make([]byte, 64<<10), 64<<20)
		send := func(value received) bool {
			select {
			case frames <- value:
				return true
			case <-done:
				return false
			}
		}
		for scanner.Scan() {
			var frame piFrame
			if err := json.Unmarshal(scanner.Bytes(), &frame); err != nil {
				send(received{err: fmt.Errorf("decode Pi response: %w", err)})
				return
			}
			if !send(received{frame: frame}) {
				return
			}
		}
		err := scanner.Err()
		if err == nil {
			err = io.ErrUnexpectedEOF
		}
		send(received{err: err})
	}()
	var lastModelError error
	for {
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case next := <-frames:
			if next.err != nil {
				return "", fmt.Errorf("Pi kernel stopped: %w", next.err)
			}
			frame := next.frame
			if frame.Type == "result" {
				if frame.Error != "" {
					if frame.Canceled {
						return frame.Text, context.Canceled
					}
					if frame.Deadline {
						return frame.Text, context.DeadlineExceeded
					}
					if lastModelError != nil {
						modelError := encodePiError(lastModelError)
						if modelError.Message == frame.Error || (frame.ErrorKind != "" && frame.ErrorKind == modelError.Kind) {
							return frame.Text, lastModelError
						}
					}
					if frame.ErrorKind != "" {
						return frame.Text, &ModelError{Kind: frame.ErrorKind, Err: errors.New(frame.Error)}
					}
					return frame.Text, errors.New(frame.Error)
				}
				if operation == "inspect" {
					if err := l.acceptPiState(frame.piState, false); err != nil {
						return "", err
					}
					if frame.TaskPrompt != "" {
						l.TaskPrompt = frame.TaskPrompt
					}
				}
				return frame.Text, nil
			}
			if frame.Type != "call" || frame.ID == "" {
				return "", errors.New("invalid Pi protocol message")
			}
			result, nextCtx, callErr := l.piCall(ctx, frame)
			if nextCtx != nil {
				ctx = nextCtx
				if operation == "run" {
					l.bridgeContext = nextCtx
				}
			}
			if callErr != nil {
				if frame.Method != "model" {
					return "", callErr
				}
				lastModelError = callErr
			} else if frame.Method == "model" {
				lastModelError = nil
			}
			reply := struct {
				Type   string   `json:"type"`
				ID     string   `json:"id"`
				Result any      `json:"result"`
				Error  *piError `json:"error,omitempty"`
			}{"reply", frame.ID, result, encodePiError(callErr)}
			if err := encoder.Encode(reply); err != nil {
				return "", fmt.Errorf("reply to Pi kernel: %w", err)
			}
		}
	}
}

func (l *Loop) piCall(ctx context.Context, frame piFrame) (any, context.Context, error) {
	switch frame.Method {
	case "input_size":
		var input struct {
			Messages []Message    `json:"messages"`
			Tools    []Definition `json:"tools"`
		}
		if err := json.Unmarshal(frame.Params, &input); err != nil {
			return nil, nil, err
		}
		size, err := l.inputBytes(input.Messages, input.Tools)
		return map[string]int{"bytes": size}, nil, err
	case "model":
		var input struct {
			Messages  []Message    `json:"messages"`
			Tools     []Definition `json:"tools"`
			MaxTokens int          `json:"maxTokens"`
		}
		if err := json.Unmarshal(frame.Params, &input); err != nil {
			return nil, nil, err
		}
		if l.Provider == nil {
			return nil, nil, errors.New("missing model provider")
		}
		message, err := l.generateMeasured(ctx, input.Messages, input.Tools, input.MaxTokens)
		if message.StopReason == "max_tokens" || message.StopReason == "length" {
			for i := range message.Content {
				block := &message.Content[i]
				if block.Type == "tool_use" && !objectArguments(block.Input) {
					// Pi blocks every truncated call. Preserve its identity while
					// replacing incomplete JSON solely for the IPC envelope.
					block.Input = json.RawMessage(`{}`)
				}
			}
		}
		return message, nil, err
	case "tool":
		var input struct {
			ID    string          `json:"id"`
			Name  string          `json:"name"`
			Input json.RawMessage `json:"input"`
		}
		if err := json.Unmarshal(frame.Params, &input); err != nil {
			return nil, nil, err
		}
		toolResult, err := l.piTool(ctx, input.Name, input.Input)
		result := map[string]any{"text": toolResult.Text, "details": toolResult.Details, "isError": err != nil}
		if err != nil {
			result["error"] = err.Error()
		}
		return result, nil, nil
	case "save":
		var state piState
		if err := json.Unmarshal(frame.Params, &state); err != nil {
			return nil, nil, err
		}
		return nil, nil, l.acceptPiState(state, true)
	case "event":
		var event Event
		if err := json.Unmarshal(frame.Params, &event); err != nil {
			return nil, nil, err
		}
		l.emit(event)
		return nil, nil, nil
	case "stop_result":
		if l.StopResult != nil {
			text, end := l.StopResult()
			return map[string]any{"text": text, "end": end}, nil, nil
		}
		return map[string]any{"end": false}, nil, nil
	case "before_request", "turn_end":
		revision := l.sessionRevision
		next := ctx
		var instruction string
		var err error
		if frame.Method == "before_request" && l.BeforeRequest != nil {
			next, err = l.BeforeRequest(ctx, l)
		}
		if frame.Method == "turn_end" {
			if l.StopResult != nil {
				if text, end := l.StopResult(); end {
					result := l.config()
					result["end"], result["text"] = true, text
					return result, nil, nil
				}
			}
			if l.OnTurnEnd != nil {
				var input struct {
					Message Message `json:"message"`
				}
				if err := json.Unmarshal(frame.Params, &input); err != nil {
					return nil, nil, err
				}
				next, instruction, err = l.OnTurnEnd(ctx, l, input.Message)
			}
		}
		if err != nil {
			return nil, nil, err
		}
		result := l.config()
		if instruction != "" {
			result["instructions"] = []string{instruction}
		}
		if revision != l.sessionRevision {
			result["session"], result["lastSequence"] = l.Checkpoint.PiSession, l.Checkpoint.LastSequence
		}
		return result, next, nil
	default:
		return nil, nil, fmt.Errorf("unknown Pi callback %q", frame.Method)
	}
}

func (l *Loop) acceptPiState(state piState, persist bool) error {
	if err := l.validatePiSession(state.Session); err != nil {
		return err
	}
	for _, message := range state.History {
		if message.Sequence > state.LastSequence {
			return errors.New("Pi projection exceeds session sequence")
		}
	}
	checkpoint := cloneCheckpoint(l.Checkpoint)
	checkpoint.Version = ContextCheckpointVersion
	checkpoint.PiSession = slices.Clone(state.Session)
	checkpoint.LastSequence = state.LastSequence
	history := cloneMessages(state.History)
	if persist && l.SaveState != nil {
		if err := l.SaveState(cloneMessages(history), cloneCheckpoint(checkpoint)); err != nil {
			return err
		}
	}
	l.History, l.Checkpoint = history, checkpoint
	l.sessionRevision++
	return nil
}

func (l *Loop) validatePiSession(raw json.RawMessage) error {
	var snapshot struct {
		Header struct {
			Type    string `json:"type"`
			Version int    `json:"version"`
			ID      string `json:"id"`
		} `json:"header"`
		Entries json.RawMessage `json:"entries"`
		File    string          `json:"file"`
		Offset  int64           `json:"offset"`
		LeafID  json.RawMessage `json:"leafId"`
		SHA256  string          `json:"sha256"`
	}
	invalid := func() error { return errors.New("invalid Pi session file checkpoint") }
	if json.Unmarshal(raw, &snapshot) != nil || snapshot.Header.Type != "session" ||
		snapshot.Header.Version != 3 || snapshot.Header.ID == "" {
		return invalid()
	}
	if len(snapshot.Entries) > 0 || l.SessionDir == "" || snapshot.File == "" || !filepath.IsAbs(snapshot.File) ||
		snapshot.Offset <= 0 || len(snapshot.LeafID) == 0 {
		return invalid()
	}
	expected, err := filepath.Abs(filepath.Join(l.SessionDir, "pi-session.jsonl"))
	if err != nil || filepath.Clean(snapshot.File) != filepath.Clean(expected) {
		return invalid()
	}
	hash, err := hex.DecodeString(snapshot.SHA256)
	if err != nil || len(hash) != 32 {
		return invalid()
	}
	return nil
}

func (l *Loop) piTool(ctx context.Context, name string, input json.RawMessage) (result ToolResult, err error) {
	defer func() {
		if failure := recover(); failure != nil {
			err = fmt.Errorf("tool panicked: %v", failure)
		}
	}()
	if l.StopResult != nil {
		if _, stopped := l.StopResult(); stopped {
			return result, errors.New("the runtime already committed a terminal result; remaining calls were not executed")
		}
	}
	if err := ctx.Err(); err != nil {
		return result, err
	}
	if l.ToolsDisabledReason != "" {
		return result, errors.New(l.ToolsDisabledReason)
	}
	for _, tool := range l.Tools {
		if tool.Name != name {
			continue
		}
		if err := ValidateArguments(tool.Schema, input); err != nil {
			return result, err
		}
		if tool.Execute == nil {
			return result, errors.New("tool has no executor")
		}
		result, err = tool.Execute(ctx, slices.Clone(input))
		result.Details = slices.Clone(result.Details)
		if len(result.Details) > 0 && !json.Valid(result.Details) {
			result.Details = nil
			err = errors.Join(err, errors.New("tool returned invalid result metadata"))
		}
		return result, err
	}
	return result, fmt.Errorf("unknown tool %q", name)
}

func piKernelPath() (string, error) {
	if configured := os.Getenv("PWNMESH_PI_RUNTIME"); configured != "" {
		path, err := filepath.Abs(configured)
		if err != nil {
			return "", err
		}
		if info, err := os.Stat(path); err != nil || info.IsDir() {
			return "", errors.New("PWNMESH_PI_RUNTIME must identify a built Pi kernel file")
		}
		return path, nil
	}
	var candidates []string
	if working, err := os.Getwd(); err == nil {
		for dir := working; ; dir = filepath.Dir(dir) {
			candidates = append(candidates, filepath.Join(dir, "runtime", "pi", "kernel.mjs"))
			if filepath.Dir(dir) == dir {
				break
			}
		}
	}
	if executable, err := os.Executable(); err == nil {
		dir := filepath.Dir(executable)
		candidates = append(candidates, filepath.Join(dir, "runtime", "pi", "kernel.mjs"),
			filepath.Join(dir, "pi", "kernel.mjs"), filepath.Join(dir, "..", "runtime", "pi", "kernel.mjs"))
	}
	candidates = append(candidates, "/opt/pwnmesh/runtime/pi/kernel.mjs", "/opt/pwnmesh/pi/kernel.mjs")
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate, nil
		}
	}
	return "", errors.New("Pi kernel is unavailable; install runtime/pi dependencies with npm ci or set PWNMESH_PI_RUNTIME")
}

func piEnvironment(environment []string) []string {
	result := make([]string, 0, len(environment))
	for _, item := range environment {
		name, _, _ := strings.Cut(item, "=")
		name = strings.ToUpper(name)
		if strings.HasPrefix(name, "ANTHROPIC") || strings.HasPrefix(name, "OPENAI") ||
			strings.Contains(name, "API_KEY") || strings.Contains(name, "AUTH_TOKEN") ||
			strings.Contains(name, "SECRET") || strings.Contains(name, "PASSWORD") ||
			strings.HasSuffix(name, "_TOKEN") || strings.HasPrefix(name, "AWS_") ||
			strings.HasPrefix(name, "GOOGLE_") || strings.HasPrefix(name, "AZURE_") ||
			name == "NODE_OPTIONS" || name == "NODE_PATH" {
			continue
		}
		result = append(result, item)
	}
	return result
}
