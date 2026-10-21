//go:build linux

package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"unicode/utf8"

	"pwnmesh/internal/agent"
)

const maxEditReplacements = 128

type replacement struct {
	Old *string `json:"oldText"`
	New *string `json:"newText"`
}

type editSpan struct {
	start, end int
	text       string
}

func (s *Set) editResult(ctx context.Context, raw json.RawMessage) (agent.ToolResult, error) {
	var a struct {
		Path  string        `json:"path"`
		Edits []replacement `json:"edits"`
	}
	if err := decode(raw, &a, "path", "edits"); err != nil {
		return agent.ToolResult{}, err
	}
	if a.Path == "" {
		return agent.ToolResult{}, errors.New("path must not be empty")
	}
	if len(a.Edits) == 0 {
		return agent.ToolResult{}, errors.New("edits must contain at least one replacement")
	}
	if len(a.Edits) > maxEditReplacements {
		return agent.ToolResult{}, fmt.Errorf("edits must contain at most %d replacements", maxEditReplacements)
	}
	if err := ctx.Err(); err != nil {
		return agent.ToolResult{}, err
	}
	path := s.path(a.Path)
	f, err := openRegular(path)
	if err != nil {
		return agent.ToolResult{}, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return agent.ToolResult{}, err
	}
	data, err := io.ReadAll(io.LimitReader(copyContextReader{ctx, f}, 16<<20+1))
	if err != nil {
		return agent.ToolResult{}, err
	}
	if len(data) > 16<<20 {
		return agent.ToolResult{}, errors.New("file is too large for edit; use a targeted command")
	}
	if !utf8.Valid(data) {
		return agent.ToolResult{}, errors.New("edit requires a UTF-8 file")
	}
	spans := make([]editSpan, 0, len(a.Edits))
	for i, edit := range a.Edits {
		if err := ctx.Err(); err != nil {
			return agent.ToolResult{}, err
		}
		if edit.Old == nil || edit.New == nil || *edit.Old == "" {
			return agent.ToolResult{}, fmt.Errorf("edit %d requires nonempty oldText and newText (which may be empty)", i+1)
		}
		old := []byte(*edit.Old)
		start := bytes.Index(data, old)
		if start < 0 || bytes.LastIndex(data, old) != start {
			return agent.ToolResult{}, fmt.Errorf("edit %d oldText must match exactly once in the original file", i+1)
		}
		spans = append(spans, editSpan{start, start + len(old), *edit.New})
	}
	sort.Slice(spans, func(i, j int) bool { return spans[i].start < spans[j].start })
	for i := 1; i < len(spans); i++ {
		if spans[i].start < spans[i-1].end {
			return agent.ToolResult{}, errors.New("edits overlap in the original file")
		}
	}
	changed := spans[:0]
	for _, span := range spans {
		if string(data[span.start:span.end]) != span.text {
			changed = append(changed, span)
		}
	}
	if len(changed) == 0 {
		return agent.ToolResult{}, errors.New("edits would not change the file")
	}
	var updated bytes.Buffer
	position := 0
	for _, span := range changed {
		if err := ctx.Err(); err != nil {
			return agent.ToolResult{}, err
		}
		updated.Write(data[position:span.start])
		updated.WriteString(span.text)
		position = span.end
	}
	updated.Write(data[position:])
	first := changed[0]
	common := 0
	for common < first.end-first.start && common < len(first.text) && data[first.start+common] == first.text[common] {
		common++
	}
	firstLine := bytes.Count(data[:first.start+common], []byte{'\n'}) + 1
	diff, err := replacementDiff(ctx, data, changed, a.Path, s.limit())
	if err != nil {
		return agent.ToolResult{}, err
	}
	if err := ctx.Err(); err != nil {
		return agent.ToolResult{}, err
	}
	if err := writeRegular(path, updated.Bytes(), info.Mode().Perm()); err != nil {
		return agent.ToolResult{}, err
	}
	details := struct {
		Diff             string `json:"diff"`
		FirstChangedLine int    `json:"firstChangedLine"`
		Edits            int    `json:"edits"`
		DiffTruncated    bool   `json:"diffTruncated"`
	}{diff.text, firstLine, len(changed), diff.truncated}
	return resultWithDetails("Edited "+a.Path+"\n"+diff.text, details), nil
}

type editDiff struct {
	text      string
	truncated bool
}

// Exact replacements already identify changed spans; no quadratic whole-file
// diff is needed. Edits touching the same line share one unified diff hunk.
func replacementDiff(ctx context.Context, data []byte, spans []editSpan, path string, limit int) (editDiff, error) {
	var out strings.Builder
	write := func(text string) bool {
		if out.Len()+len(text) > limit {
			return false
		}
		out.WriteString(text)
		return true
	}
	clipped := func() (editDiff, error) { return editDiff{out.String() + "[Diff truncated.]\n", true}, nil }
	if !write("--- " + path + "\n+++ " + path + "\n") {
		return clipped()
	}
	lineDelta := 0
	for index := 0; index < len(spans); {
		if err := ctx.Err(); err != nil {
			return editDiff{}, err
		}
		first := spans[index]
		start := bytes.LastIndexByte(data[:first.start], '\n') + 1
		end := editLineEnd(data, first.end)
		last := index + 1
		var next string
		for {
			if err := ctx.Err(); err != nil {
				return editDiff{}, err
			}
			for last < len(spans) && spans[last].start < end {
				end = editLineEnd(data, spans[last].end)
				last++
			}
			var replacement strings.Builder
			position := start
			for _, span := range spans[index:last] {
				if err := ctx.Err(); err != nil {
					return editDiff{}, err
				}
				replacement.Write(data[position:span.start])
				replacement.WriteString(span.text)
				position = span.end
			}
			replacement.Write(data[position:end])
			next = replacement.String()
			// Removing a line terminator joins the following line. Include it
			// so the hunk describes the resulting full line, not a false EOF.
			if end == len(data) || strings.HasSuffix(next, "\n") {
				break
			}
			end = editLineEnd(data, end+1)
		}
		old := string(data[start:end])
		oldLine := bytes.Count(data[:start], []byte{'\n'}) + 1
		oldCount, newCount := diffLines(old), diffLines(next)
		newLine := oldLine + lineDelta
		if newCount == 0 {
			newLine--
		}
		if !write(fmt.Sprintf("@@ -%d,%d +%d,%d @@\n", oldLine, oldCount, newLine, newCount)) {
			return clipped()
		}
		for _, side := range []struct{ prefix, text string }{{"-", old}, {"+", next}} {
			remaining := side.text
			for remaining != "" {
				if err := ctx.Err(); err != nil {
					return editDiff{}, err
				}
				line, rest, newline := strings.Cut(remaining, "\n")
				if !write(side.prefix + line + "\n") {
					return clipped()
				}
				if !newline && !write("\\ No newline at end of file\n") {
					return clipped()
				}
				remaining = rest
			}
		}
		lineDelta += newCount - oldCount
		index = last
	}
	return editDiff{out.String(), false}, nil
}

func editLineEnd(data []byte, end int) int {
	if newline := bytes.IndexByte(data[end-1:], '\n'); newline >= 0 {
		return end - 1 + newline + 1
	}
	return len(data)
}

func diffLines(text string) int {
	count := strings.Count(text, "\n")
	if text != "" && !strings.HasSuffix(text, "\n") {
		count++
	}
	return count
}
