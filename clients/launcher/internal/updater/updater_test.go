package updater

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
