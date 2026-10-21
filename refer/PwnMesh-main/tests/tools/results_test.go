//go:build linux

package tools_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/tools"
)

func toolSet(t *testing.T, limit int) (string, map[string]agent.Tool) {
	t.Helper()
	dir := t.TempDir()
	set := tools.Set{Dir: dir, RunDir: t.TempDir(), OutputBytes: limit}
	available := map[string]agent.Tool{}
	for _, tool := range set.All() {
		available[tool.Name] = tool
	}
	return dir, available
}

func invoke(t *testing.T, tool agent.Tool, args any) (agent.ToolResult, error) {
	t.Helper()
	raw, err := json.Marshal(args)
	if err != nil {
		t.Fatal(err)
	}
	if tool.Execute == nil {
		t.Fatalf("%s has no structured result", tool.Name)
	}
	return tool.Execute(context.Background(), raw)
}

func TestReadContinuationUsesWholeLinesAtBothLimits(t *testing.T) {
	dir, available := toolSet(t, 8)
	path := filepath.Join(dir, "input.txt")
	if err := os.WriteFile(path, []byte("a\n你好\nlast\n"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		args map[string]any
		text string
		next int
		by   string
	}{
		{map[string]any{"path": path}, "a\n", 2, "bytes"},
		{map[string]any{"path": path, "offset": 2}, "你好\n", 3, "bytes"},
		{map[string]any{"path": path, "limit": 1}, "a\n", 2, "lines"},
		{map[string]any{"path": path, "offset": 3}, "last\n", 0, ""},
	} {
		result, err := invoke(t, available["read"], test.args)
		if err != nil || !strings.HasPrefix(result.Text, test.text) || !utf8.ValidString(result.Text) {
			t.Fatalf("read = %+v, %v", result, err)
		}
		var details struct {
			NextOffset     int    `json:"nextOffset"`
			TruncatedBy    string `json:"truncatedBy"`
			Complete       bool   `json:"complete"`
			OutputBytes    int    `json:"outputBytes"`
			SourcePath     string `json:"sourcePath"`
			FullOutputPath string `json:"fullOutputPath"`
		}
		if err := json.Unmarshal(result.Details, &details); err != nil {
			t.Fatal(err)
		}
		if details.NextOffset != test.next || details.TruncatedBy != test.by || details.Complete != (test.next == 0) || details.OutputBytes != len(test.text) || details.SourcePath != path || details.FullOutputPath != "" {
			t.Fatalf("details = %+v, want next=%d by=%q", details, test.next, test.by)
		}
		if test.next > 0 && !strings.Contains(result.Text, "offset=") {
			t.Fatal("continuation is absent from model-visible text")
		}
	}
}

func TestReadHugeFirstLineReturnsNoMisleadingContinuation(t *testing.T) {
	dir, available := toolSet(t, 4)
	path := filepath.Join(dir, "long.txt")
	if err := os.WriteFile(path, []byte("你好你好\nnext\n"), 0600); err != nil {
		t.Fatal(err)
	}
	result, err := invoke(t, available["read"], map[string]any{"path": path})
	if err != nil {
		t.Fatal(err)
	}
	var details struct {
		NextOffset            int  `json:"nextOffset"`
		FirstLineExceedsLimit bool `json:"firstLineExceedsLimit"`
		OutputBytes           int  `json:"outputBytes"`
	}
	if err := json.Unmarshal(result.Details, &details); err != nil {
		t.Fatal(err)
	}
	if details.NextOffset != 1 || !details.FirstLineExceedsLimit || details.OutputBytes != 0 || !strings.Contains(result.Text, "use bash") {
		t.Fatalf("result = %+v; details = %+v", result, details)
	}
}

func TestEditsUseOriginalFileAndReturnDiff(t *testing.T) {
	dir, available := toolSet(t, 32000)
	path := filepath.Join(dir, "script.sh")
	original := "header\nalpha\nomega\n"
	if err := os.WriteFile(path, []byte(original), 0755); err != nil {
		t.Fatal(err)
	}
	result, err := invoke(t, available["edit"], map[string]any{"path": path, "edits": []map[string]string{
		{"oldText": "omega", "newText": "done"},
		{"oldText": "alpha", "newText": "omega\nextra"},
	}})
	if err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(path)
	if err != nil || string(got) != "header\nomega\nextra\ndone\n" {
		t.Fatalf("file = %q, %v", got, err)
	}
	var details struct {
		Diff             string `json:"diff"`
		FirstChangedLine int    `json:"firstChangedLine"`
		Edits            int    `json:"edits"`
	}
	if err := json.Unmarshal(result.Details, &details); err != nil {
		t.Fatal(err)
	}
	if details.FirstChangedLine != 2 || details.Edits != 2 || !strings.Contains(details.Diff, "@@ -3,1 +4,1 @@") || !strings.Contains(details.Diff, "+done") {
		t.Fatalf("edit details = %+v", details)
	}
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0755 {
		t.Fatalf("mode was not preserved: %v, %v", info, err)
	}
}

func TestEditValidationNeverWritesPartialBatch(t *testing.T) {
	dir, available := toolSet(t, 32000)
	path := filepath.Join(dir, "input.txt")
	original := "abcdef\naaa\n"
	for _, edits := range [][]map[string]string{
		{{"oldText": "abc", "newText": "x"}, {"oldText": "bcde", "newText": "y"}},
		{{"oldText": "abc", "newText": "x"}, {"oldText": "missing", "newText": "y"}},
		{{"oldText": "aa", "newText": "x"}},
	} {
		if err := os.WriteFile(path, []byte(original), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := invoke(t, available["edit"], map[string]any{"path": path, "edits": edits}); err == nil {
			t.Fatal("invalid batch was accepted")
		}
		got, err := os.ReadFile(path)
		if err != nil || string(got) != original {
			t.Fatalf("invalid batch changed file: %q, %v", got, err)
		}
	}
}

func TestEditRejectsOversizedBatchBeforeOpeningFile(t *testing.T) {
	dir, available := toolSet(t, 32000)
	path := filepath.Join(dir, "input.txt")
	original := "original\n"
	if err := os.WriteFile(path, []byte(original), 0600); err != nil {
		t.Fatal(err)
	}
	edits := make([]map[string]string, 129)
	for i := range edits {
		edits[i] = map[string]string{"oldText": "original", "newText": "updated"}
	}
	for _, target := range []string{path, filepath.Join(dir, "missing.txt")} {
		if _, err := invoke(t, available["edit"], map[string]any{"path": target, "edits": edits}); err == nil || !strings.Contains(err.Error(), "at most 128 replacements") {
			t.Fatalf("oversized batch reached file validation: %v", err)
		}
	}
	got, err := os.ReadFile(path)
	if err != nil || string(got) != original {
		t.Fatalf("oversized batch changed the file: %q, %v", got, err)
	}
	var schema struct {
		Properties struct {
			Edits struct {
				MaxItems int `json:"maxItems"`
			} `json:"edits"`
		} `json:"properties"`
	}
	if err := json.Unmarshal(available["edit"].Schema, &schema); err != nil || schema.Properties.Edits.MaxItems != 128 {
		t.Fatalf("tool schema does not advertise the batch limit: %+v, %v", schema, err)
	}
}

func TestEditDiffIncludesLinesJoinedByNewlineRemoval(t *testing.T) {
	dir, available := toolSet(t, 32000)
	path := filepath.Join(dir, "input.txt")
	if err := os.WriteFile(path, []byte("alpha\nbeta\n"), 0600); err != nil {
		t.Fatal(err)
	}
	result, err := invoke(t, available["edit"], map[string]any{"path": path, "edits": []map[string]string{{"oldText": "alpha\n", "newText": "a"}}})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(result.Text, "@@ -1,2 +1,1 @@\n-alpha\n-beta\n+abeta\n") {
		t.Fatalf("joined-line diff = %q", result.Text)
	}
}

func TestEditRejectsTopLevelReplacementWithoutWriting(t *testing.T) {
	dir, available := toolSet(t, 32000)
	path := filepath.Join(dir, "input.txt")
	if err := os.WriteFile(path, []byte("original"), 0600); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(map[string]string{"path": path, "oldText": "original", "newText": "changed"})
	if err != nil {
		t.Fatal(err)
	}
	if err := agent.ValidateArguments(available["edit"].Schema, raw); err == nil {
		t.Fatal("tool schema accepted obsolete top-level replacement")
	}
	if _, err := available["edit"].Execute(context.Background(), raw); err == nil {
		t.Fatal("tool silently accepted obsolete top-level replacement")
	}
	data, err := os.ReadFile(path)
	if err != nil || string(data) != "original" {
		t.Fatalf("rejected input changed file: %q, %v", data, err)
	}
}

func TestEditsOnSameLineShareOneDiffHunk(t *testing.T) {
	dir, available := toolSet(t, 32000)
	path := filepath.Join(dir, "input.txt")
	if err := os.WriteFile(path, []byte("alpha beta gamma\n"), 0600); err != nil {
		t.Fatal(err)
	}
	result, err := invoke(t, available["edit"], map[string]any{"path": path, "edits": []map[string]string{
		{"oldText": "alpha", "newText": "first"},
		{"oldText": "gamma", "newText": "last"},
	}})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Count(result.Text, "@@ -") != 1 || !strings.Contains(result.Text, "-alpha beta gamma\n+first beta last\n") {
		t.Fatalf("same-line diff = %q", result.Text)
	}
}

func TestBashDetailsRetainHashedOutputAndDistinguishFailure(t *testing.T) {
	_, available := toolSet(t, 6)
	result, err := invoke(t, available["bash"], map[string]any{"command": "printf 'abcdefghijk'; exit 3"})
	if err == nil {
		t.Fatal("expected nonzero command exit")
	}
	var details struct {
		Truncated      bool   `json:"truncated"`
		Complete       bool   `json:"complete"`
		FullOutputPath string `json:"fullOutputPath"`
		TotalBytes     int64  `json:"totalBytes"`
	}
	if err := json.Unmarshal(result.Details, &details); err != nil {
		t.Fatal(err)
	}
	content, readErr := os.ReadFile(details.FullOutputPath)
	digest := sha256.Sum256(content)
	if readErr != nil || string(content) != "abcdefghijk" || !details.Truncated || !details.Complete || details.TotalBytes != 11 ||
		filepath.Base(details.FullOutputPath) != "output-"+hex.EncodeToString(digest[:])+".txt" {
		t.Fatalf("details = %+v; retained=%q, %v", details, content, readErr)
	}
}

func TestBashCancellationMarksRetainedOutputIncomplete(t *testing.T) {
	_, available := toolSet(t, 4)
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	result, err := available["bash"].Execute(ctx, json.RawMessage(`{"command":"printf 'abcdefghijk'; sleep 30"}`))
	if err == nil {
		t.Fatal("cancellation succeeded unexpectedly")
	}
	var details struct {
		Complete       bool   `json:"complete"`
		FullOutputPath string `json:"fullOutputPath"`
	}
	if err := json.Unmarshal(result.Details, &details); err != nil {
		t.Fatal(err)
	}
	if details.Complete || !strings.Contains(result.Text, "incomplete") || details.FullOutputPath == "" {
		t.Fatalf("cancelled output = %+v, %+v", result, details)
	}
	if _, err := os.Stat(details.FullOutputPath); err != nil {
		t.Fatal(err)
	}
}

func TestSearchAndListRetainOutputDetails(t *testing.T) {
	for _, name := range []string{"grep", "find", "ls"} {
		t.Run(name, func(t *testing.T) {
			dir, available := toolSet(t, 4)
			path := filepath.Join(dir, "long-name.txt")
			if err := os.WriteFile(path, []byte("needle\n"), 0600); err != nil {
				t.Fatal(err)
			}
			args := map[string]any{"path": dir}
			if name == "grep" {
				args["pattern"] = "needle"
			} else if name == "find" {
				args["pattern"] = "*.txt"
			}
			result, err := invoke(t, available[name], args)
			if err != nil {
				t.Fatal(err)
			}
			var details struct {
				Truncated      bool   `json:"truncated"`
				Complete       bool   `json:"complete"`
				FullOutputPath string `json:"fullOutputPath"`
				OutputBytes    int    `json:"outputBytes"`
				TotalBytes     int64  `json:"totalBytes"`
			}
			if err := json.Unmarshal(result.Details, &details); err != nil {
				t.Fatal(err)
			}
			content, readErr := os.ReadFile(details.FullOutputPath)
			digest := sha256.Sum256(content)
			if readErr != nil || !strings.Contains(string(content), "long-name.txt") || !details.Truncated || !details.Complete ||
				details.OutputBytes != 4 || details.TotalBytes != int64(len(content)) || !strings.Contains(result.Text, details.FullOutputPath) ||
				filepath.Base(details.FullOutputPath) != "output-"+hex.EncodeToString(digest[:])+".txt" {
				t.Fatalf("result = %+v; details = %+v; retained=%q, %v", result, details, content, readErr)
			}
		})
	}
}

func TestSearchNoMatchesRetainsDetailsAndRejectsReadErrors(t *testing.T) {
	for _, name := range []string{"grep", "find"} {
		t.Run(name, func(t *testing.T) {
			dir, available := toolSet(t, 32000)
			args := map[string]any{"path": dir, "pattern": "missing"}
			result, err := invoke(t, available[name], args)
			var details struct {
				Complete    bool  `json:"complete"`
				OutputBytes int   `json:"outputBytes"`
				TotalBytes  int64 `json:"totalBytes"`
			}
			if err != nil || result.Text != "No matches" || json.Unmarshal(result.Details, &details) != nil ||
				!details.Complete || details.OutputBytes != 0 || details.TotalBytes != 0 {
				t.Fatalf("no matches = %+v, %+v, %v", result, details, err)
			}
			args["path"] = filepath.Join(dir, "absent")
			result, err = invoke(t, available[name], args)
			if err == nil || result.Text == "No matches" || len(result.Details) == 0 {
				t.Fatalf("read failure was discarded: %+v, %v", result, err)
			}
		})
	}
}
