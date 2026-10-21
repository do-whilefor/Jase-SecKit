//go:build linux

package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"pwnmesh/internal/agent"
)

type runtimeToolCapability struct {
	Name          string `json:"name"`
	Available     bool   `json:"available"`
	Path          string `json:"path,omitempty"`
	Version       string `json:"version,omitempty"`
	VersionStatus string `json:"version_status"`
}

func runtimeCapabilitiesTool(workspace, workingDir, runDir string) agent.Tool {
	return agent.Tool{Definition: agent.Definition{
		Name: "runtime_capabilities", Description: "Inspect common local tool versions, browser executable, network configuration and shared/working/output directories. The tool catalog is not exhaustive. No target requests; availability does not prove browser launch or network reachability.",
		Schema: json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`),
	}, Execute: agent.TextExecutor(func(ctx context.Context, raw json.RawMessage) (string, error) {
		if trimmed := bytes.TrimSpace(raw); len(trimmed) == 0 || trimmed[0] != '{' {
			return "", errors.New("runtime_capabilities expects one empty object")
		}
		var input struct{}
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&input); err != nil {
			return "", err
		}
		if err := decoder.Decode(&input); err != io.EOF {
			return "", errors.New("runtime_capabilities expects one empty object")
		}
		specs := []struct{ name, flag string }{
			{"bash", "--version"}, {"curl", "--version"}, {"python3", "--version"},
			{"node", "--version"}, {"rg", "--version"}, {"nmap", "--version"},
			{"nuclei", "-version"}, {"ffuf", "-V"}, {"sqlmap", "--version"},
			{"pwn-http", "--version"}, {"playwright-cli", "--version"},
		}
		found := make([]runtimeToolCapability, len(specs))
		var group sync.WaitGroup
		for i, spec := range specs {
			group.Add(1)
			go func() {
				defer group.Done()
				found[i] = probeRuntimeTool(ctx, workingDir, spec.name, spec.flag)
			}()
		}
		group.Wait()
		if err := ctx.Err(); err != nil {
			return "", err
		}
		browserPath := os.Getenv("PLAYWRIGHT_MCP_EXECUTABLE_PATH")
		if browserPath == "" {
			browserPath = "pwnmesh-chromium"
		}
		browser := probeRuntimeTool(ctx, workingDir, browserPath, "--version")
		if err := ctx.Err(); err != nil {
			return "", err
		}
		browser.Name = "chromium"
		if configured := os.Getenv("PLAYWRIGHT_MCP_BROWSER"); configured != "" {
			browser.Name = configured
		}
		mode := os.Getenv("PWNMESH_NETWORK_MODE")
		if mode == "" {
			mode = "unknown"
		}
		connection := os.Getenv("PWNMESH_CONNECTION_MODE")
		if connection != "direct" && connection != "proxy" {
			connection = "inherited"
		}
		proxy := false
		for _, key := range []string{"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"} {
			proxy = proxy || os.Getenv(key) != ""
		}
		absoluteWorkspace, _ := filepath.Abs(workspace)
		absoluteWorkingDir, _ := filepath.Abs(workingDir)
		absoluteRunDir, _ := filepath.Abs(runDir)
		result, err := json.Marshal(map[string]any{
			"observed_at": time.Now().UTC().Format(time.RFC3339Nano),
			"workspace":   absoluteWorkspace, "working_directory": absoluteWorkingDir, "output_directory": absoluteRunDir,
			"tools": found, "tool_catalog_complete": false,
			"browsers": []runtimeToolCapability{browser}, "browser_launch_verified": false,
			"network": map[string]any{"container_mode": mode, "connection_mode": connection,
				"proxy_environment_configured": proxy, "reachability": "not_probed"},
		})
		return string(result), err
	})}
}

// Version checks are local, bounded and never invoke a shell or contact targets.
func probeRuntimeTool(parent context.Context, dir, name, flag string) runtimeToolCapability {
	result := runtimeToolCapability{Name: name, VersionStatus: "unavailable"}
	path, err := exec.LookPath(name)
	if err != nil {
		return result
	}
	result.Available, result.Path = true, path
	ctx, cancel := context.WithTimeout(parent, time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, flag)
	cmd.Dir = dir
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	cmd.WaitDelay = 100 * time.Millisecond
	output := &capabilityOutput{}
	cmd.Stdout, cmd.Stderr = output, output
	if err := cmd.Run(); err != nil {
		result.VersionStatus = "probe_failed"
		return result
	}
	line, _, _ := strings.Cut(strings.TrimSpace(output.String()), "\n")
	line = redactTraceCredentials(line)
	if len(line) > 256 {
		line = line[:256]
	}
	result.Version = strings.ToValidUTF8(line, "")
	result.VersionStatus = "observed"
	if result.Version == "" {
		result.VersionStatus = "unknown"
	}
	return result
}

type capabilityOutput struct{ bytes.Buffer }

func (b *capabilityOutput) Write(p []byte) (int, error) {
	n := len(p)
	if remaining := 4096 - b.Len(); remaining > 0 {
		_, _ = b.Buffer.Write(p[:min(n, remaining)])
	}
	return n, nil
}
