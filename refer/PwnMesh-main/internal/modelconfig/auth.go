package modelconfig

import (
	"os"
	"path/filepath"
)

// OAuth refresh credentials remain in the settings owner's writable store.
func AuthDir(settingsPath string) string {
	if dir := os.Getenv("PWNMESH_AUTH_DIR"); dir != "" {
		return dir
	}
	if settingsPath == "" {
		settingsPath, _ = ResolvePath()
	}
	return filepath.Join(filepath.Dir(settingsPath), "model-auth")
}
