//go:build darwin

package cmd

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
)

// stubSecurityBinary creates a tiny shim "security" binary in a temp
// dir and prepends that dir to PATH for the duration of the test. The
// shim mimics `security find-generic-password -s "Claude Code-credentials"`
// based on the SECURITY_TEST_BEHAVIOR env var:
//
//	"exists" → exit 0 with one line of fake metadata on stdout
//	"absent" → exit 44 ("item not found") with the canonical stderr msg
//
// 44 is the exit code real `security` uses for missing items
// (errSecItemNotFound, -25300, mapped through to 44 by the CLI). We
// don't actually assert on the exit code in production code, but
// matching it keeps the shim faithful.
func stubSecurityBinary(t *testing.T, behavior string) {
	if runtime.GOOS != "darwin" {
		t.Skip("darwin only")
	}
	t.Helper()
	dir := t.TempDir()
	shim := filepath.Join(dir, "security")
	src := `#!/bin/sh
case "$SECURITY_TEST_BEHAVIOR" in
  exists) echo 'attributes: <SecKeychainAttribute>'; exit 0 ;;
  absent) echo 'security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.' >&2; exit 44 ;;
esac
exit 1
`
	if err := os.WriteFile(shim, []byte(src), 0o755); err != nil {
		t.Fatalf("write shim: %v", err)
	}
	origPath := os.Getenv("PATH")
	t.Setenv("PATH", dir+":"+origPath)
	t.Setenv("SECURITY_TEST_BEHAVIOR", behavior)
	// Sanity-check the shim resolves first on PATH.
	resolved, err := exec.LookPath("security")
	if err != nil {
		t.Fatalf("shim not on PATH: %v", err)
	}
	if resolved != shim {
		t.Fatalf("shim not earliest on PATH: resolved %q want %q", resolved, shim)
	}
}

func TestProbeClaudeCredentials_NotFound(t *testing.T) {
	stubSecurityBinary(t, "absent")
	// Force a fake HOME so we don't pick up the developer's real
	// ~/.claude/.credentials.json by accident — the not-found branch
	// returns early before checking the file, but be defensive.
	t.Setenv("HOME", t.TempDir())
	got := probeClaudeCredentials()
	if got != keychainItemNotFound {
		t.Fatalf("expected keychainItemNotFound (%d), got %d",
			keychainItemNotFound, got)
	}
}

func TestProbeClaudeCredentials_ItemPresentFileAbsent(t *testing.T) {
	stubSecurityBinary(t, "exists")
	home := t.TempDir()
	t.Setenv("HOME", home)
	// Parent dir present but no .credentials.json — this is the
	// silent-401 case.
	if err := os.MkdirAll(filepath.Join(home, ".claude"), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	got := probeClaudeCredentials()
	if got != keychainItemPresentFileAbsent {
		t.Fatalf("expected keychainItemPresentFileAbsent (%d), got %d",
			keychainItemPresentFileAbsent, got)
	}
}

func TestProbeClaudeCredentials_ItemPresentFilePresent(t *testing.T) {
	stubSecurityBinary(t, "exists")
	home := t.TempDir()
	t.Setenv("HOME", home)
	credsDir := filepath.Join(home, ".claude")
	if err := os.MkdirAll(credsDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	credsFile := filepath.Join(credsDir, ".credentials.json")
	if err := os.WriteFile(credsFile, []byte(`{"claudeAiOauth":{}}`), 0o600); err != nil {
		t.Fatalf("write creds: %v", err)
	}
	got := probeClaudeCredentials()
	if got != keychainItemPresentFilePresent {
		t.Fatalf("expected keychainItemPresentFilePresent (%d), got %d",
			keychainItemPresentFilePresent, got)
	}
}
