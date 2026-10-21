//go:build linux

package tools

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"

	"pwnmesh/internal/agent"
)

func (s *Set) readResult(ctx context.Context, raw json.RawMessage) (agent.ToolResult, error) {
	var a struct {
		Path   string `json:"path"`
		Offset int    `json:"offset"`
		Limit  int    `json:"limit"`
	}
	if err := decode(raw, &a, "path"); err != nil {
		return agent.ToolResult{}, err
	}
	if a.Path == "" {
		return agent.ToolResult{}, errors.New("path must not be empty")
	}
	if a.Offset < 0 || a.Limit < 0 {
		return agent.ToolResult{}, errors.New("offset and limit must be positive")
	}
	if a.Offset == 0 {
		a.Offset = 1
	}
	if a.Limit == 0 {
		a.Limit = 2000
	}
	f, err := openRegular(s.path(a.Path))
	if err != nil {
		return agent.ToolResult{}, err
	}
	defer f.Close()
	details := outputDetails{Complete: true, SourcePath: s.path(a.Path)}
	if info, statErr := f.Stat(); statErr == nil {
		details.TotalBytes = info.Size()
	}
	reader := bufio.NewReader(copyContextReader{ctx, f})
	var output, current strings.Builder
	line := 1
	for {
		if err = ctx.Err(); err != nil {
			break
		}
		piece, readErr := reader.ReadSlice('\n')
		if readErr != nil && readErr != io.EOF && readErr != bufio.ErrBufferFull {
			err = readErr
			break
		}
		if line >= a.Offset {
			if output.Len()+current.Len()+len(piece) > s.limit() {
				details.Truncated, details.TruncatedBy = true, "bytes"
				details.FirstLineExceedsLimit = details.OutputLines == 0
				break
			}
			current.Write(piece)
		}
		if readErr == bufio.ErrBufferFull {
			continue
		}
		if line >= a.Offset && current.Len() > 0 {
			output.WriteString(current.String())
			current.Reset()
			details.OutputLines++
		}
		if readErr == io.EOF {
			break
		}
		line++
		if details.OutputLines >= a.Limit {
			if _, peekErr := reader.Peek(1); peekErr == nil {
				details.Truncated, details.TruncatedBy = true, "lines"
			} else if peekErr != io.EOF {
				err = peekErr
			}
			break
		}
	}
	details.OutputBytes = output.Len()
	details.Complete = err == nil && !details.Truncated
	text := strings.ToValidUTF8(output.String(), "�")
	if details.Truncated {
		details.NextOffset = a.Offset + details.OutputLines
		if details.FirstLineExceedsLimit {
			text += fmt.Sprintf("\n[Line %d exceeds the %d-byte read limit; use bash to inspect part of this line. nextOffset=%d.]", details.NextOffset, s.limit(), details.NextOffset)
		} else {
			text += fmt.Sprintf("\n[Read limited by %s; continue reading %s with offset=%d. nextOffset=%d.]", details.TruncatedBy, a.Path, details.NextOffset, details.NextOffset)
		}
	}
	return resultWithDetails(text, details), err
}
