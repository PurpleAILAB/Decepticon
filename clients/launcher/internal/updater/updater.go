package updater

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

const (
	Repo       = "PurpleAILAB/Decepticon"
	APIBaseURL = "https://api.github.com/repos/" + Repo
	RawBaseURL = "https://raw.githubusercontent.com/" + Repo
)

// Release represents a GitHub release.
type Release struct {
	TagName string  `json:"tag_name"`
	Assets  []Asset `json:"assets"`
}

// Asset represents a release asset (binary download).
type Asset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
}

// FetchLatestRelease gets the latest release info from GitHub.
func FetchLatestRelease() (*Release, error) {
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(APIBaseURL + "/releases/latest")
	if err != nil {
		return nil, fmt.Errorf("fetch release: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub API returned %d", resp.StatusCode)
	}

	var release Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return nil, fmt.Errorf("decode release: %w", err)
	}
	return &release, nil
}

// CompareVersions returns true if latest > current using numeric semver comparison.
func CompareVersions(current, latest string) bool {
	current = strings.TrimPrefix(current, "v")
	latest = strings.TrimPrefix(latest, "v")
	if current == "dev" || current == "" {
		return false // Don't auto-update dev builds
	}
	return compareSemver(current, latest) < 0
}

// compareSemver compares two semver strings numerically. Returns -1, 0, or 1.
func compareSemver(a, b string) int {
	aParts := strings.SplitN(a, ".", 3)
	bParts := strings.SplitN(b, ".", 3)
	for i := 0; i < 3; i++ {
		var av, bv int
		if i < len(aParts) {
			fmt.Sscanf(aParts[i], "%d", &av)
		}
		if i < len(bParts) {
			fmt.Sscanf(bParts[i], "%d", &bv)
		}
		if av < bv {
			return -1
		}
		if av > bv {
			return 1
		}
	}
	return 0
}

// SyncConfigFiles downloads updated docker-compose.yml and litellm.yaml.
func SyncConfigFiles(branch string) error {
	home := config.DecepticonHome()
	files := map[string]string{
		"docker-compose.yml":   filepath.Join(home, "docker-compose.yml"),
		"config/litellm.yaml":  filepath.Join(home, "config", "litellm.yaml"),
	}

	client := &http.Client{Timeout: 30 * time.Second}
	for src, dst := range files {
		if err := downloadFile(client, fmt.Sprintf("%s/%s/%s", RawBaseURL, branch, src), dst); err != nil {
			return fmt.Errorf("%s: %w", src, err)
		}
		ui.Success("Updated " + src)
	}
	return nil
}

// downloadFile fetches a URL and writes it to dst, closing the body properly.
func downloadFile(client *http.Client, url, dst string) error {
	resp, err := client.Get(url)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download: HTTP %d", resp.StatusCode)
	}

	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read: %w", err)
	}

	return os.WriteFile(dst, data, 0o644)
}

// SelfUpdate downloads and replaces the current binary.
func SelfUpdate(release *Release) error {
	assetName := fmt.Sprintf("decepticon-%s-%s", runtime.GOOS, runtime.GOARCH)

	var downloadURL string
	for _, asset := range release.Assets {
		if asset.Name == assetName {
			downloadURL = asset.BrowserDownloadURL
			break
		}
	}
	if downloadURL == "" {
		return fmt.Errorf("no binary found for %s/%s in release %s", runtime.GOOS, runtime.GOARCH, release.TagName)
	}

	ui.Info("Downloading " + assetName + "...")
	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("download binary: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download binary: HTTP %d", resp.StatusCode)
	}

	// Write to temp file first
	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("get executable path: %w", err)
	}

	tmpPath := execPath + ".tmp"
	tmp, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}

	if _, err := io.Copy(tmp, resp.Body); err != nil {
		tmp.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("write binary: %w", err)
	}
	tmp.Close()

	// Atomic replace
	if err := os.Rename(tmpPath, execPath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("replace binary: %w", err)
	}

	ui.Success("Binary updated to " + release.TagName)
	return nil
}

// WriteVersion writes the version to .version file.
func WriteVersion(version string) error {
	versionFile := filepath.Join(config.DecepticonHome(), ".version")
	return os.WriteFile(versionFile, []byte(strings.TrimPrefix(version, "v")), 0o644)
}

// CheckAndUpdate performs auto-update check. Returns true if update was applied.
//
// Update order is binary-first, then config files. If the binary update fails
// we abort entirely so we never end up with new compose/litellm files driving
// an old launcher (which has caused breakage in past releases when image
// tags or compose schema changed). If config sync fails after a successful
// binary update we keep the new binary and leave .version unwritten so the
// next launch retries config sync.
func CheckAndUpdate(currentVersion string, env map[string]string) bool {
	if config.Get(env, "AUTO_UPDATE", "true") == "false" {
		return false
	}

	release, err := FetchLatestRelease()
	if err != nil {
		return false // Silent fail for auto-update
	}

	if !CompareVersions(currentVersion, release.TagName) {
		return false
	}

	ui.Info(fmt.Sprintf("Update available: %s → %s", currentVersion, release.TagName))

	if err := SelfUpdate(release); err != nil {
		ui.Warning("Self-update failed: " + err.Error())
		return false
	}

	// Use release tag for config files to avoid main branch drift
	ref := release.TagName // e.g., "v1.0.7"
	if err := SyncConfigFiles(ref); err != nil {
		ui.Warning("Binary updated but config sync failed: " + err.Error())
		ui.Warning("Run 'decepticon update' to retry config sync.")
		// Do not WriteVersion — leaving .version stale lets the next run
		// retry the sync via this same code path.
		return true
	}

	_ = WriteVersion(release.TagName)
	return true
}
