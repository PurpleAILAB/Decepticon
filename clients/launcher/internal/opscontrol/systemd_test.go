package opscontrol

import (
	"os"
	"path/filepath"
	"testing"
)

// TestRemoveStaleDropIns_DeletesDeadBinaryOverride covers the v1.1.10
// dogfood regression: a `systemctl edit` override from an earlier test
// pinned ExecStart= to /tmp/decepticon-stop-v3 (since deleted), and
// the launcher kept silently re-using it on `install`.
func TestRemoveStaleDropIns_DeletesDeadBinaryOverride(t *testing.T) {
	tmp := t.TempDir()
	dropInDir := filepath.Join(tmp, "decepticon-opscontrol.service.d")
	if err := os.MkdirAll(dropInDir, 0o755); err != nil {
		t.Fatalf("mkdir drop-in: %v", err)
	}
	staleBin := filepath.Join(tmp, "definitely-not-a-real-binary")
	overrideBody := "[Service]\nExecStart=\nExecStart=" + staleBin + " opscontrol daemon\n"
	overridePath := filepath.Join(dropInDir, "override.conf")
	if err := os.WriteFile(overridePath, []byte(overrideBody), 0o644); err != nil {
		t.Fatalf("write override: %v", err)
	}

	s := &SystemdManager{UnitName: "decepticon-opscontrol"}
	if !s.removeStaleDropIns(dropInDir) {
		t.Fatalf("expected stale drop-in removal, got false")
	}
	if _, err := os.Stat(overridePath); !os.IsNotExist(err) {
		t.Errorf("override.conf should be removed; stat err=%v", err)
	}
	// Drop-in directory is now empty, so it should also be gone — keeps
	// `systemctl edit` from re-opening a ghost directory.
	if _, err := os.Stat(dropInDir); !os.IsNotExist(err) {
		t.Errorf("empty drop-in dir should be removed; stat err=%v", err)
	}
}

// TestRemoveStaleDropIns_KeepsLiveBinaryOverride is the safety contract:
// an operator's legitimate override (custom env vars, restart policy
// tweaks) that points to a real binary must survive install.
func TestRemoveStaleDropIns_KeepsLiveBinaryOverride(t *testing.T) {
	tmp := t.TempDir()
	dropInDir := filepath.Join(tmp, "decepticon-opscontrol.service.d")
	if err := os.MkdirAll(dropInDir, 0o755); err != nil {
		t.Fatalf("mkdir drop-in: %v", err)
	}
	// Use the test binary itself as the "live" ExecStart target.
	liveBin, err := os.Executable()
	if err != nil {
		t.Fatalf("locate test binary: %v", err)
	}
	overrideBody := "[Service]\nExecStart=\nExecStart=" + liveBin + " opscontrol daemon\n"
	overridePath := filepath.Join(dropInDir, "override.conf")
	if err := os.WriteFile(overridePath, []byte(overrideBody), 0o644); err != nil {
		t.Fatalf("write override: %v", err)
	}

	s := &SystemdManager{UnitName: "decepticon-opscontrol"}
	if s.removeStaleDropIns(dropInDir) {
		t.Fatalf("live drop-in should not be removed")
	}
	if _, err := os.Stat(overridePath); err != nil {
		t.Errorf("override.conf should still exist; stat err=%v", err)
	}
}

// TestRemoveStaleDropIns_AcceptsModifierPrefixes covers systemd's
// ExecStart modifier syntax (- @ : + ! !!) so we don't false-positive
// or false-negative on operator overrides that use them.
func TestRemoveStaleDropIns_AcceptsModifierPrefixes(t *testing.T) {
	tmp := t.TempDir()
	dropInDir := filepath.Join(tmp, "decepticon-opscontrol.service.d")
	if err := os.MkdirAll(dropInDir, 0o755); err != nil {
		t.Fatalf("mkdir drop-in: %v", err)
	}
	staleBin := filepath.Join(tmp, "ghost-binary")
	for _, prefix := range []string{"-", "@", ":", "+", "!", "!!"} {
		sub := filepath.Join(dropInDir, "case-"+prefix+".conf")
		body := "[Service]\nExecStart=\nExecStart=" + prefix + staleBin + " opscontrol daemon\n"
		if err := os.WriteFile(sub, []byte(body), 0o644); err != nil {
			t.Fatalf("write override: %v", err)
		}
	}

	s := &SystemdManager{UnitName: "decepticon-opscontrol"}
	if !s.removeStaleDropIns(dropInDir) {
		t.Fatalf("expected stale removal across modifier prefixes")
	}
}

// TestRemoveStaleDropIns_NoDirIsNoop guards against panic / error
// when there's never been a drop-in (the common case on fresh installs).
func TestRemoveStaleDropIns_NoDirIsNoop(t *testing.T) {
	s := &SystemdManager{UnitName: "decepticon-opscontrol"}
	if s.removeStaleDropIns(filepath.Join(t.TempDir(), "does-not-exist")) {
		t.Fatalf("missing drop-in dir should not report removal")
	}
}
