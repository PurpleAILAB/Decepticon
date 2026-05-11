package cmd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---- backupWorkspace ----

func TestBackupWorkspace_RenameSucceeds(t *testing.T) {
	// On the same filesystem os.Rename succeeds; src is gone, dst has the files.
	src := t.TempDir()
	dst := filepath.Join(t.TempDir(), "backup")

	if err := os.WriteFile(filepath.Join(src, "data.txt"), []byte("hello"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := backupWorkspace(src, dst); err != nil {
		t.Fatalf("backupWorkspace: %v", err)
	}

	got, err := os.ReadFile(filepath.Join(dst, "data.txt"))
	if err != nil {
		t.Fatalf("ReadFile at dst: %v", err)
	}
	if string(got) != "hello" {
		t.Errorf("dst content = %q, want %q", got, "hello")
	}
	if _, err := os.Stat(src); !os.IsNotExist(err) {
		t.Error("src should be gone after rename")
	}
}

func TestBackupWorkspace_TargetAlreadyExists(t *testing.T) {
	src := t.TempDir()
	dst := t.TempDir() // dst already exists

	err := backupWorkspace(src, dst)
	if err == nil {
		t.Fatal("expected error when dst already exists, got nil")
	}
	if !strings.Contains(err.Error(), "already exists") {
		t.Errorf("error %q should mention 'already exists'", err)
	}
}

// ---- copyDirAll ----

func TestCopyDirAll_SingleFile(t *testing.T) {
	src := t.TempDir()
	dst := filepath.Join(t.TempDir(), "out")

	if err := os.WriteFile(filepath.Join(src, "file.txt"), []byte("content"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := copyDirAll(src, dst); err != nil {
		t.Fatalf("copyDirAll: %v", err)
	}

	got, err := os.ReadFile(filepath.Join(dst, "file.txt"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(got) != "content" {
		t.Errorf("content = %q, want %q", got, "content")
	}
}

func TestCopyDirAll_NestedDirectories(t *testing.T) {
	src := t.TempDir()
	dst := filepath.Join(t.TempDir(), "out")

	structure := map[string]string{
		"a/b/deep.txt": "deep",
		"a/mid.txt":    "mid",
		"root.txt":     "root",
	}
	for rel, content := range structure {
		full := filepath.Join(src, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	if err := copyDirAll(src, dst); err != nil {
		t.Fatalf("copyDirAll: %v", err)
	}

	for rel, want := range structure {
		got, err := os.ReadFile(filepath.Join(dst, filepath.FromSlash(rel)))
		if err != nil {
			t.Errorf("ReadFile %s: %v", rel, err)
			continue
		}
		if string(got) != want {
			t.Errorf("%s: got %q, want %q", rel, got, want)
		}
	}
}

func TestCopyDirAll_EmptySubdirectory(t *testing.T) {
	src := t.TempDir()
	dst := filepath.Join(t.TempDir(), "out")

	if err := os.MkdirAll(filepath.Join(src, "emptydir"), 0o755); err != nil {
		t.Fatal(err)
	}

	if err := copyDirAll(src, dst); err != nil {
		t.Fatalf("copyDirAll: %v", err)
	}

	info, err := os.Stat(filepath.Join(dst, "emptydir"))
	if err != nil {
		t.Fatalf("Stat emptydir at dst: %v", err)
	}
	if !info.IsDir() {
		t.Error("emptydir should be a directory at dst")
	}
}

func TestCopyDirAll_PreservesFilePermissions(t *testing.T) {
	src := t.TempDir()
	dst := filepath.Join(t.TempDir(), "out")

	srcFile := filepath.Join(src, "exec.sh")
	if err := os.WriteFile(srcFile, []byte("#!/bin/sh"), 0o755); err != nil {
		t.Fatal(err)
	}

	if err := copyDirAll(src, dst); err != nil {
		t.Fatalf("copyDirAll: %v", err)
	}

	info, err := os.Stat(filepath.Join(dst, "exec.sh"))
	if err != nil {
		t.Fatalf("Stat dst file: %v", err)
	}
	// Check the executable bits are set (owner execute at minimum).
	if info.Mode()&0o100 == 0 {
		t.Errorf("execute bit not set; mode = %v", info.Mode())
	}
}

// ---- cleanPathFromFile ----

func writeRC(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "rc")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func readRC(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile %s: %v", path, err)
	}
	return string(b)
}

func TestCleanPathFromFile_RemovesBashBlock(t *testing.T) {
	rc := writeRC(t, "export FOO=bar\n\n# decepticon\nexport PATH=\"$HOME/.local/bin:$PATH\"\nexport BAZ=qux\n")
	cleanPathFromFile(rc)

	got := readRC(t, rc)
	if strings.Contains(got, "decepticon") {
		t.Errorf("marker line should be removed; got:\n%s", got)
	}
	if strings.Contains(got, ".local/bin") {
		t.Errorf("PATH export line should be removed; got:\n%s", got)
	}
	if !strings.Contains(got, "export FOO=bar") || !strings.Contains(got, "export BAZ=qux") {
		t.Errorf("unrelated lines should be preserved; got:\n%s", got)
	}
}

func TestCleanPathFromFile_RemovesFishBlock(t *testing.T) {
	rc := writeRC(t, "set -x FOO bar\n# decepticon\nfish_add_path $HOME/.local/bin\nset -x BAZ qux\n")
	cleanPathFromFile(rc)

	got := readRC(t, rc)
	if strings.Contains(got, "decepticon") || strings.Contains(got, "fish_add_path") {
		t.Errorf("fish block should be removed; got:\n%s", got)
	}
	if !strings.Contains(got, "set -x FOO bar") || !strings.Contains(got, "set -x BAZ qux") {
		t.Errorf("unrelated lines should be preserved; got:\n%s", got)
	}
}

func TestCleanPathFromFile_RemovesPrecedingBlankLine(t *testing.T) {
	rc := writeRC(t, "export FOO=bar\n\n# decepticon\nexport PATH=\"$HOME/.local/bin:$PATH\"\n")
	cleanPathFromFile(rc)

	got := readRC(t, rc)
	// The blank line before the marker should also be stripped.
	if strings.Contains(got, "\n\n") {
		t.Errorf("preceding blank line should be removed; got:\n%q", got)
	}
}

func TestCleanPathFromFile_PreservesUnrelatedPathLines(t *testing.T) {
	rc := writeRC(t, "export PATH=\"$HOME/go/bin:$PATH\"\nexport PATH=\"$HOME/.local/bin:$PATH\"\n")
	cleanPathFromFile(rc)

	got := readRC(t, rc)
	// Neither line has the "# decepticon" marker so both should survive.
	if !strings.Contains(got, "go/bin") {
		t.Errorf("unrelated PATH line should be preserved; got:\n%s", got)
	}
	if !strings.Contains(got, ".local/bin") {
		t.Errorf("standalone .local/bin line (no marker) should be preserved; got:\n%s", got)
	}
}

func TestCleanPathFromFile_FileNotExist(t *testing.T) {
	// Should be a no-op rather than panicking or returning an error.
	cleanPathFromFile(filepath.Join(t.TempDir(), "nonexistent_rc"))
}

func TestCleanPathFromFile_NoChangesNeeded(t *testing.T) {
	content := "export FOO=bar\nexport BAZ=qux\n"
	rc := writeRC(t, content)
	cleanPathFromFile(rc)

	got := readRC(t, rc)
	if got != content {
		t.Errorf("file should be unchanged; got %q, want %q", got, content)
	}
}
