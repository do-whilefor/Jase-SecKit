//go:build linux

package tools

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"syscall"
)

// Clipped previews must identify all retained bytes, including their omitted
// middle. A random capture path makes identical observations appear different.
func retainOutput(ctx context.Context, source *os.File) (string, error) {
	original := source.Name()
	digest, size, err := outputDigest(ctx, source)
	if err != nil {
		return original, err
	}
	target := filepath.Join(filepath.Dir(original), "output-"+digest+".txt")
	if err := os.Link(original, target); err != nil {
		if !errors.Is(err, os.ErrExist) {
			return original, err
		}
		// Never follow or overwrite a preexisting path. Matching names alone
		// do not establish that retained evidence still has the expected bytes.
		existing, err := os.OpenFile(target, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
		if err != nil {
			return original, err
		}
		defer existing.Close()
		actual, actualSize, err := outputDigest(ctx, existing)
		if err != nil {
			return original, err
		}
		if actual != digest || actualSize != size {
			return original, errors.New("retained output content does not match its identity")
		}
	} else {
		info, statErr := os.Lstat(target)
		sourceInfo, sourceErr := source.Stat()
		if statErr != nil || sourceErr != nil {
			return original, errors.Join(statErr, sourceErr)
		}
		if !info.Mode().IsRegular() || !os.SameFile(info, sourceInfo) {
			return original, errors.New("retained output path changed during publication")
		}
	}
	return target, os.Remove(original)
}

func outputDigest(ctx context.Context, file *os.File) (string, int64, error) {
	info, err := file.Stat()
	if err != nil {
		return "", 0, err
	}
	if !info.Mode().IsRegular() || info.Size() > maxOutputFileBytes {
		return "", 0, errors.New("retained output must be a bounded regular file")
	}
	if _, err := file.Seek(0, 0); err != nil {
		return "", 0, err
	}
	digest := sha256.New()
	size, err := io.Copy(digest, io.LimitReader(copyContextReader{ctx, file}, maxOutputFileBytes+1))
	if err != nil {
		return "", 0, err
	}
	if size > maxOutputFileBytes || size != info.Size() {
		return "", 0, errors.New("retained output changed while reading")
	}
	return hex.EncodeToString(digest.Sum(nil)), size, nil
}
