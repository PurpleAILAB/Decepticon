package updater

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestCompareVersions(t *testing.T) {
	tests := []struct {
		current, latest string
		want            bool
	}{
		{"1.0.0", "1.1.0", true},
		{"1.1.0", "1.0.0", false},
		{"1.0.0", "1.0.0", false},
		{"v1.0.0", "v1.1.0", true},
		{"dev", "1.0.0", false},
		{"", "1.0.0", false},
		// Numeric semver: 1.9 → 1.10 must trigger update
		{"1.9.0", "1.10.0", true},
		{"1.10.0", "1.9.0", false},
		{"2.0.0", "1.99.99", false},
		{"0.9.9", "1.0.0", true},
	}
	for _, tt := range tests {
		got := CompareVersions(tt.current, tt.latest)
		if got != tt.want {
			t.Errorf("CompareVersions(%q, %q) = %v, want %v", tt.current, tt.latest, got, tt.want)
		}
	}
}

func TestDisplayVersion(t *testing.T) {
	tests := map[string]string{
		"1.0.22":  "v1.0.22",
		"v1.0.22": "v1.0.22",
		"dev":     "dev",
		"":        "",
	}
	for input, want := range tests {
		if got := displayVersion(input); got != want {
			t.Errorf("displayVersion(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestFetchLatestRelease_Mock(t *testing.T) {
	release := Release{
		TagName: "v1.2.0",
		Assets: []Asset{
			{Name: "decepticon-linux-amd64", BrowserDownloadURL: "https://example.com/binary"},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(release)
	}))
	defer server.Close()

	// Can't easily test FetchLatestRelease without changing the URL,
	// so we test the JSON parsing directly
	resp, err := http.Get(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	var got Release
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}

	if got.TagName != "v1.2.0" {
		t.Errorf("TagName = %q, want v1.2.0", got.TagName)
	}
	if len(got.Assets) != 1 || got.Assets[0].Name != "decepticon-linux-amd64" {
		t.Errorf("Assets = %v", got.Assets)
	}
}

func TestPromptIfUpdateAvailable_SkipsDevBuilds(t *testing.T) {
	// "dev" / empty version means a local build that does not track
	// published releases — no prompt, no GitHub round-trip.
	for _, v := range []string{"dev", ""} {
		applied, err := PromptIfUpdateAvailable(v)
		if err != nil {
			t.Errorf("PromptIfUpdateAvailable(%q) err = %v", v, err)
		}
		if applied {
			t.Errorf("PromptIfUpdateAvailable(%q) applied=true, want false", v)
		}
	}
}

func TestPromptIfUpdateAvailable_SkipsNonInteractive(t *testing.T) {
	// Test runs are always non-interactive (stdin is the test harness
	// pipe), so PromptIfUpdateAvailable must fall straight through
	// without ever calling huh.Run. A non-zero version that would
	// otherwise fail the "is dev?" gate is safe — the function returns
	// silently on the TTY check before fetching anything.
	applied, err := PromptIfUpdateAvailable("0.0.0")
	if err != nil {
		t.Errorf("PromptIfUpdateAvailable err = %v", err)
	}
	if applied {
		t.Errorf("PromptIfUpdateAvailable applied=true, want false (no TTY)")
	}
}

func TestApplyUpdate_NilRelease(t *testing.T) {
	if err := ApplyUpdate(nil, "main"); err == nil {
		t.Error("ApplyUpdate(nil, ...) err = nil, want non-nil")
	}
}

// ---- downloadFile ----

func TestDownloadFile_Success(t *testing.T) {
	want := "hello from mock server"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, want)
	}))
	defer server.Close()

	dst := filepath.Join(t.TempDir(), "out.txt")
	if err := downloadFile(&http.Client{}, server.URL, dst); err != nil {
		t.Fatalf("downloadFile: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(got) != want {
		t.Errorf("content = %q, want %q", got, want)
	}
}

func TestDownloadFile_HTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	err := downloadFile(&http.Client{}, server.URL, filepath.Join(t.TempDir(), "out.txt"))
	if err == nil {
		t.Fatal("expected error for HTTP 500, got nil")
	}
	if !strings.Contains(err.Error(), "HTTP 500") {
		t.Errorf("error %q should contain 'HTTP 500'", err)
	}
}

func TestDownloadFile_CreatesParentDirectory(t *testing.T) {
	want := "nested content"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, want)
	}))
	defer server.Close()

	// dst is three levels deep inside a dir that doesn't exist yet.
	dst := filepath.Join(t.TempDir(), "a", "b", "c", "out.txt")
	if err := downloadFile(&http.Client{}, server.URL, dst); err != nil {
		t.Fatalf("downloadFile: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(got) != want {
		t.Errorf("content = %q, want %q", got, want)
	}
}

func TestDownloadFile_NetworkError(t *testing.T) {
	// Start then immediately close the server so the port is unreachable.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := server.URL
	server.Close()

	err := downloadFile(&http.Client{}, url, filepath.Join(t.TempDir(), "out.txt"))
	if err == nil {
		t.Fatal("expected error for closed server, got nil")
	}
}

// ---- SelfUpdate ----

func TestSelfUpdate_NoMatchingAsset(t *testing.T) {
	// A release whose only asset targets a different platform should
	// fail with an error that names the current GOOS/GOARCH so the
	// operator knows why the binary was not replaced.
	release := &Release{
		TagName: "v9.9.9",
		Assets:  []Asset{{Name: "decepticon-plan9-mips", BrowserDownloadURL: "http://localhost/plan9"}},
	}
	err := SelfUpdate(release)
	if err == nil {
		t.Fatal("SelfUpdate with no matching asset: expected error, got nil")
	}
	if !strings.Contains(err.Error(), runtime.GOOS) || !strings.Contains(err.Error(), runtime.GOARCH) {
		t.Errorf("error %q should mention GOOS=%s GOARCH=%s", err, runtime.GOOS, runtime.GOARCH)
	}
}

func TestSelfUpdate_DownloadHTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer server.Close()

	assetName := fmt.Sprintf("decepticon-%s-%s", runtime.GOOS, runtime.GOARCH)
	release := &Release{
		TagName: "v9.9.9",
		Assets:  []Asset{{Name: assetName, BrowserDownloadURL: server.URL + "/binary"}},
	}
	if err := SelfUpdate(release); err == nil {
		t.Fatal("SelfUpdate with HTTP 403: expected error, got nil")
	}
}

func TestSelfUpdate_WritesAndRenames(t *testing.T) {
	// Verify that on a successful download the binary is written to
	// execPath and the .tmp file is removed.
	binaryContent := []byte("fake binary content for testing")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(binaryContent)
	}))
	defer server.Close()

	dir := t.TempDir()
	fakeBin := filepath.Join(dir, "decepticon")

	// Redirect executableFn so SelfUpdate writes into our temp dir instead
	// of clobbering the running test binary. Matches the isWSLFn pattern.
	orig := executableFn
	executableFn = func() (string, error) { return fakeBin, nil }
	t.Cleanup(func() { executableFn = orig })

	assetName := fmt.Sprintf("decepticon-%s-%s", runtime.GOOS, runtime.GOARCH)
	release := &Release{
		TagName: "v9.9.9",
		Assets:  []Asset{{Name: assetName, BrowserDownloadURL: server.URL + "/binary"}},
	}
	if err := SelfUpdate(release); err != nil {
		t.Fatalf("SelfUpdate: %v", err)
	}

	got, err := os.ReadFile(fakeBin)
	if err != nil {
		t.Fatalf("ReadFile after SelfUpdate: %v", err)
	}
	if string(got) != string(binaryContent) {
		t.Errorf("binary content = %q, want %q", got, binaryContent)
	}
	// The temp file must be cleaned up by the rename.
	if _, statErr := os.Stat(fakeBin + ".tmp"); !os.IsNotExist(statErr) {
		t.Error(".tmp file should not exist after a successful rename")
	}
}

// ---- WriteVersion ----

func TestWriteVersion_StripsVPrefix(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("DECEPTICON_HOME", dir)

	if err := WriteVersion("v2.3.4"); err != nil {
		t.Fatalf("WriteVersion: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(dir, ".version"))
	if err != nil {
		t.Fatalf("ReadFile .version: %v", err)
	}
	if string(got) != "2.3.4" {
		t.Errorf(".version = %q, want %q", got, "2.3.4")
	}
}

func TestWriteVersion_NoPrefix(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("DECEPTICON_HOME", dir)

	if err := WriteVersion("1.0.0"); err != nil {
		t.Fatalf("WriteVersion: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(dir, ".version"))
	if err != nil {
		t.Fatalf("ReadFile .version: %v", err)
	}
	if string(got) != "1.0.0" {
		t.Errorf(".version = %q, want %q", got, "1.0.0")
	}
}

// ---- ApplyUpdate ----

func TestApplyUpdate_SelfUpdateErrorPropagates(t *testing.T) {
	// SyncConfigFiles and compose.Pull failures are downgraded to warnings;
	// only SelfUpdate failure is returned as an error. A release with no
	// asset for the current platform forces SelfUpdate to fail so we can
	// verify the error is propagated and labelled correctly.
	release := &Release{
		TagName: "v9.9.9",
		Assets:  []Asset{{Name: "decepticon-plan9-mips", BrowserDownloadURL: "http://localhost/plan9"}},
	}
	err := ApplyUpdate(release, "v9.9.9")
	if err == nil {
		t.Fatal("ApplyUpdate with failing SelfUpdate: expected error, got nil")
	}
	if !strings.Contains(err.Error(), "binary update") {
		t.Errorf("error %q should contain 'binary update'", err)
	}
}
