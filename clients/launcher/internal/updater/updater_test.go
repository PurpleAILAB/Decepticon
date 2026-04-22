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
