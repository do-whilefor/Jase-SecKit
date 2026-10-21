package dispatcher

import (
	"context"
	"io"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/protocol"
)

func (s *Scheduler) configureInputReader() {
	setter, ok := s.Runner.(interface {
		SetInputReader(func(context.Context, protocol.Job, board.InputFile) (io.ReadCloser, error))
	})
	if !ok {
		return
	}
	setter.SetInputReader(func(ctx context.Context, job protocol.Job, file board.InputFile) (io.ReadCloser, error) {
		return s.Client.OpenInput(ctx, job, file)
	})
}
