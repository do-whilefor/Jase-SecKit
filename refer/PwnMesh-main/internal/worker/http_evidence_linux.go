//go:build linux

package worker

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"

	"golang.org/x/sys/unix"
)

var httpEvidenceFiles = map[string]string{
	"request": "request.json", "request_body": "request.body",
	"response": "response.json", "response_body": "response.body", "error": "error.json",
}

func validHTTPReceipt(result map[string]any, output string, retained map[string]any) bool {
	refs, ok := result["evidence"].(map[string]any)
	if !ok {
		return false
	}
	status, hasStatus := result["status"].(json.Number)
	code, err := status.Int64()
	if result["status"] != nil && (!hasStatus || err != nil || code < 100 || code > 999) {
		return false
	}
	for key, value := range refs {
		name, known := httpEvidenceFiles[key]
		ref, ok := value.(map[string]any)
		if !known || !ok || ref["path"] != filepath.Join(output, name) {
			return false
		}
		digest, ok := ref["sha256"].(string)
		decoded, err := hex.DecodeString(digest)
		if !ok || err != nil || len(decoded) != sha256.Size {
			return false
		}
		count, ok := ref["bytes"].(json.Number)
		size, err := count.Int64()
		actual, exists := retained[key].(map[string]any)
		if !ok || err != nil || size < 0 || !exists || actual["bytes"] != size {
			return false
		}
		// Large files remain referenceable with explicit hash_limit metadata.
		// Never echo an unverified digest as if Worker had checked it.
		if actual["reason"] != "hash_limit" && actual["sha256"] != digest {
			return false
		}
	}
	if result["complete"] != true {
		return true
	}
	if !hasStatus || code < 200 || result["error"] != nil {
		return false
	}
	for _, key := range []string{"request", "request_body", "response", "response_body"} {
		if refs[key] == nil {
			return false
		}
	}
	return true
}

// Read evidence independently of subprocess claims. Never follow substituted
// links or hash an unbounded stream, including when the process was interrupted.
func retainedHTTPReferences(dir string) map[string]any {
	refs := make(map[string]any)
	fd, err := unix.Open(dir, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
	if err != nil {
		return refs
	}
	defer unix.Close(fd)
	for key, name := range httpEvidenceFiles {
		path := filepath.Join(dir, name)
		child, err := unix.Openat(fd, name, unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
		if err != nil {
			continue
		}
		file := os.NewFile(uintptr(child), path)
		stat, err := file.Stat()
		if err != nil || !stat.Mode().IsRegular() {
			file.Close()
			continue
		}
		const maxHashBytes = 64 << 20
		if stat.Size() > maxHashBytes {
			file.Close()
			refs[key] = map[string]any{"path": path, "bytes": stat.Size(), "available": false, "reason": "hash_limit"}
			continue
		}
		hash := sha256.New()
		size, err := io.Copy(hash, io.LimitReader(file, maxHashBytes+1))
		file.Close()
		if err == nil && size == stat.Size() {
			refs[key] = map[string]any{"path": path, "sha256": hex.EncodeToString(hash.Sum(nil)), "bytes": size}
		} else {
			refs[key] = map[string]any{"path": path, "available": false, "reason": "hash_unavailable"}
		}
	}
	return refs
}
