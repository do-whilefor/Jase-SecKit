//go:build linux

package worker_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/tools"
)

func TestScriptReuseCopiesAndEditsRetainedBytes(t *testing.T) {
	workspace := t.TempDir()
	script := "#!/usr/bin/env bash\nset -eu\nlabel='caf\u00e9'\nprintf '%s\\n' \"$label: ${1:-original}\"\n"
	if err := os.WriteFile(filepath.Join(workspace, "original.sh"), []byte(script), 0755); err != nil {
		t.Fatal(err)
	}
	set := tools.Set{Dir: workspace, RunDir: t.TempDir()}
	available := make(map[string]agent.Tool)
	for _, tool := range set.All() {
		available[tool.Definition.Name] = tool
	}
	call := func(name string, args any) string {
		t.Helper()
		raw, err := json.Marshal(args)
		if err != nil {
			t.Fatal(err)
		}
		result, err := available[name].Execute(context.Background(), raw)
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		return result.Text
	}
	hash := sha256.Sum256([]byte(script))
	digest := hex.EncodeToString(hash[:])
	receipt := call("write", map[string]string{
		"path": "variant.sh", "source_path": "original.sh", "source_sha256": digest,
	})
	var copied struct {
		Mode         string `json:"mode"`
		Bytes        int    `json:"bytes"`
		SHA256       string `json:"sha256"`
		SourceSHA256 string `json:"source_sha256"`
	}
	if err := json.Unmarshal([]byte(receipt), &copied); err != nil {
		t.Fatal(err)
	}
	if copied.Mode != "copied" || copied.Bytes != len(script) || copied.SHA256 != digest || copied.SourceSHA256 != digest {
		t.Fatalf("copy receipt: %+v", copied)
	}
	assertFile := func(path, want string) {
		t.Helper()
		got, err := os.ReadFile(filepath.Join(workspace, path))
		if err != nil || string(got) != want {
			t.Fatalf("%s: bytes=%q error=%v", path, got, err)
		}
	}
	assertFile("variant.sh", script)
	call("edit", map[string]any{"path": "variant.sh", "edits": []map[string]string{{"oldText": "${1:-original}", "newText": "${1:-variant}"}}})
	assertFile("variant.sh", strings.Replace(script, "${1:-original}", "${1:-variant}", 1))
	assertFile("original.sh", script)
}
