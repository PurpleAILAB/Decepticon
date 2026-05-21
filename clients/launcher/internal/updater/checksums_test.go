package updater

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Verifies that the manifest parser tolerates the formatting variations
// `sha256sum` and similar tools actually emit: standard two-space
// separator, the `*` binary-mode prefix, leading/trailing whitespace,
// and blank lines.
func TestParseChecksumManifest(t *testing.T) {
	in := strings.NewReader(strings.Join([]string{
		"",                                                                       // blank line — must be skipped
		"abc123  decepticon-linux-amd64",                                         // standard
		"deadbeef *config-checksums.txt",                                         // sha256sum binary-mode marker
		"  feedface  docker-compose.yml  ",                                       // leading/trailing whitespace
		"cafebabec0ffee deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef", // single-space sep
	}, "\n"))

	m, err := parseChecksumManifest(in)
	if err != nil {
		t.Fatalf("parseChecksumManifest returned error: %v", err)
	}

	cases := map[string]string{
		"decepticon-linux-amd64": "abc123",
		"config-checksums.txt":   "deadbeef",
		"docker-compose.yml":     "feedface",
	}
	for path, want := range cases {
		got, ok := m[path]
		if !ok {
			t.Errorf("missing entry for %q", path)
			continue
		}
		if got != want {
			t.Errorf("entry %q: got %q, want %q", path, got, want)
		}
	}
}

// Rejects manifest lines that don't have at least <hex> <path>; a
// malformed manifest must fail loudly rather than silently lose
// entries — that's the entire point of the integrity check.
func TestParseChecksumManifestRejectsMalformed(t *testing.T) {
	_, err := parseChecksumManifest(strings.NewReader("only-one-field"))
	if err == nil {
		t.Fatal("expected error for malformed line, got nil")
	}
}

func TestSha256FileAndVerify(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "payload")
	if err := os.WriteFile(target, []byte("hello\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	// Expected SHA-256 of "hello\n" — independently computable with
	// `printf 'hello\n' | sha256sum`. Pinning the literal value protects
	// against accidental algorithm changes (e.g. trimming the trailing
	// newline) and serves as the canonical fixture for future tests.
	const wantHash = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"

	got, err := sha256File(target)
	if err != nil {
		t.Fatalf("sha256File: %v", err)
	}
	if got != wantHash {
		t.Fatalf("sha256File: got %q, want %q", got, wantHash)
	}

	manifest := map[string]string{"payload": wantHash}
	if err := verifyAgainstManifest(target, "payload", manifest); err != nil {
		t.Errorf("verifyAgainstManifest happy path: %v", err)
	}

	bad := map[string]string{"payload": "0000000000000000000000000000000000000000000000000000000000000000"}
	if err := verifyAgainstManifest(target, "payload", bad); err == nil {
		t.Error("verifyAgainstManifest: expected mismatch error, got nil")
	}

	missing := map[string]string{}
	if err := verifyAgainstManifest(target, "payload", missing); err == nil {
		t.Error("verifyAgainstManifest: expected missing-entry error, got nil")
	}
}
