package updater

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"charm.land/huh/v2"
	"golang.org/x/term"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

// ConfigManifestAsset is the name of the sha256sum-format manifest the
// release workflow uploads alongside the Go binaries. It pins
// docker-compose.yml, config/litellm.yaml, and .env.example.
const ConfigManifestAsset = "config-checksums.txt"

// BinaryChecksumsAsset is GoReleaser's binary checksum manifest. Same
// "<hex>  <name>" format as ConfigManifestAsset.
const BinaryChecksumsAsset = "checksums.txt"

const (
	Repo       = "PurpleAILAB/Decepticon"
	APIBaseURL = "https://api.github.com/repos/" + Repo
	RawBaseURL = "https://raw.githubusercontent.com/" + Repo
)

// executableFn is a var so tests can redirect binary writes to a temp dir
// instead of overwriting the test binary itself. Matches the isWSLFn /
// wslHostIPFn pattern used in cmd/start.go.
var executableFn = os.Executable

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
		return false // Dev builds do not track published releases.
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
//
// When “release“ is non-nil AND the release exposes a
// “config-checksums.txt“ asset, every downloaded file is verified
// against the manifest before being written to the install dir.
// raw.githubusercontent.com (where the config files live) is served
// from GitHub's CDN; the release asset is the authoritative integrity
// pin for the same tag.
//
// Branch-tracking installs (DECEPTICON_BRANCH set in .env, no release
// asset available) fall back to the legacy download-without-verify
// behavior with a warning. “release == nil“ exists for this path.
func SyncConfigFiles(branch string, release *Release) error {
	home := config.DecepticonHome()
	files := map[string]string{
		"docker-compose.yml":            filepath.Join(home, "docker-compose.yml"),
		"docker-compose.opscontrol.yml": filepath.Join(home, "docker-compose.opscontrol.yml"),
		"config/litellm.yaml":           filepath.Join(home, "config", "litellm.yaml"),
	}

	client := &http.Client{Timeout: 30 * time.Second}

	manifest, err := fetchManifest(client, release, ConfigManifestAsset)
	if err != nil {
		return err
	}

	for src, dst := range files {
		url := fmt.Sprintf("%s/%s/%s", RawBaseURL, branch, src)
		tmp := dst + ".tmp"
		defer os.Remove(tmp)
		if err := downloadFile(client, url, tmp); err != nil {
			return fmt.Errorf("%s: %w", src, err)
		}
		if manifest != nil {
			if err := verifyAgainstManifest(tmp, src, manifest); err != nil {
				return fmt.Errorf("%s: %w", src, err)
			}
		}
		if err := os.Rename(tmp, dst); err != nil {
			return fmt.Errorf("%s: rename: %w", src, err)
		}
		ui.Success("Updated " + src)
	}
	return nil
}

// fetchManifest downloads a sha256sum-format manifest asset from the
// given release and returns it as a map of "manifest path → hex digest".
// Returns (nil, nil) when “release“ is nil OR the asset is absent
// (branch-tracking installs and pre-1.0.27 releases respectively); the
// caller treats that as legacy mode and skips per-file verification.
func fetchManifest(client *http.Client, release *Release, assetName string) (map[string]string, error) {
	if release == nil {
		ui.Warning("No release pinned for sync — skipping checksum verification (branch mode).")
		return nil, nil
	}
	url := assetURL(release, assetName)
	if url == "" {
		ui.Warning(fmt.Sprintf(
			"%s missing from release %s — skipping checksum verification (pre-1.0.27 release).",
			assetName, release.TagName,
		))
		return nil, nil
	}
	resp, err := client.Get(url)
	if err != nil {
		return nil, fmt.Errorf("download %s: %w", assetName, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("download %s: HTTP %d", assetName, resp.StatusCode)
	}
	return parseChecksumManifest(resp.Body)
}

// parseChecksumManifest reads sha256sum format ("<hex>  <path>" or
// "<hex> *<path>") and returns a {path: hex} map. Whitespace-only and
// empty lines are tolerated; malformed lines are rejected so a corrupted
// manifest cannot silently lose entries.
func parseChecksumManifest(r io.Reader) (map[string]string, error) {
	out := map[string]string{}
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		// "<hex>  <path>" — split on the first whitespace run; the
		// remainder is the path. Tolerate the optional " *" prefix
		// (sha256sum's binary-mode marker).
		fields := strings.Fields(line)
		if len(fields) < 2 {
			return nil, fmt.Errorf("malformed manifest line: %q", line)
		}
		hash := fields[0]
		path := strings.TrimPrefix(strings.Join(fields[1:], " "), "*")
		out[path] = hash
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}
	return out, nil
}

// verifyAgainstManifest computes the sha256 of dst and compares it
// against the entry for “manifestPath“ in the supplied manifest map.
func verifyAgainstManifest(dst, manifestPath string, manifest map[string]string) error {
	expected, ok := manifest[manifestPath]
	if !ok {
		return fmt.Errorf("no checksum entry for %q in manifest", manifestPath)
	}
	actual, err := sha256File(dst)
	if err != nil {
		return fmt.Errorf("hash %s: %w", dst, err)
	}
	if actual != expected {
		return fmt.Errorf("checksum mismatch for %s\n  expected: %s\n  got:      %s", manifestPath, expected, actual)
	}
	return nil
}

// sha256File returns the lower-case hex SHA-256 of path's contents.
func sha256File(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// assetURL returns the browser_download_url for the named asset, or "".
func assetURL(release *Release, name string) string {
	if release == nil {
		return ""
	}
	for _, a := range release.Assets {
		if a.Name == name {
			return a.BrowserDownloadURL
		}
	}
	return ""
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

	return os.WriteFile(dst, data, 0o600)
}

// SelfUpdate downloads and replaces the current binary. The download is
// verified against “checksums.txt“ (GoReleaser-produced) before the
// atomic rename — a tampered binary on the GitHub CDN never reaches
// disk in the executable path. Releases that predate checksum
// verification (no “checksums.txt“ asset) emit a warning and fall
// back to the legacy unverified replace.
func SelfUpdate(release *Release) error {
	assetName := fmt.Sprintf("decepticon-%s-%s", runtime.GOOS, runtime.GOARCH)

	downloadURL := assetURL(release, assetName)
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
	execPath, err := executableFn()
	if err != nil {
		return fmt.Errorf("get executable path: %w", err)
	}

	tmpPath := execPath + ".tmp"
	// Create temp file owner-only so an unverified binary is never
	// world-readable or executable. Chmod to 0o755 happens only after
	// checksum verification succeeds, immediately before the rename.
	tmp, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}

	if _, err := io.Copy(tmp, resp.Body); err != nil {
		tmp.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("write binary: %w", err)
	}
	tmp.Close()

	// Verify the downloaded binary before swapping it into place. If the
	// release predates checksum publishing (pre-1.0.27) fetchManifest
	// returns (nil, nil) and we skip with a warning — that keeps existing
	// upgrade paths working while the new check rolls out.
	manifest, err := fetchManifest(client, release, BinaryChecksumsAsset)
	if err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("fetch binary checksums: %w", err)
	}
	if manifest != nil {
		if err := verifyAgainstManifest(tmpPath, assetName, manifest); err != nil {
			os.Remove(tmpPath)
			return fmt.Errorf("verify binary: %w", err)
		}
	}

	// Verification passed — make the binary executable before renaming.
	if err := os.Chmod(tmpPath, 0o755); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("chmod temp file: %w", err)
	}

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

// NotifyIfUpdateAvailable checks GitHub releases and prints a non-blocking
// update notice. It never mutates the binary, config files, or Docker images;
// users apply updates explicitly with `decepticon update`.
//
// Used as the fallback path when “PromptIfUpdateAvailable“ cannot present
// an interactive prompt (e.g. stdin is not a TTY in CI / piped invocation).
func NotifyIfUpdateAvailable(currentVersion string) bool {
	release, err := FetchLatestRelease()
	if err != nil {
		return false // Silent fail; startup should not depend on GitHub.
	}

	if !CompareVersions(currentVersion, release.TagName) {
		return false
	}

	ui.Info(fmt.Sprintf("Update available: %s -> %s", displayVersion(currentVersion), release.TagName))
	ui.DimText("Run `decepticon update` to upgrade.")
	return true
}

// ApplyUpdate runs the full upgrade flow: SyncConfigFiles, Docker image
// pull, SelfUpdate (binary), WriteVersion. Shared between the
// “decepticon update“ command and the interactive launch-time prompt.
//
// “ref“ is the git ref used for “SyncConfigFiles“ — “release.TagName“
// for tagged releases, or a branch name for development tracking.
//
// Errors from individual steps are surfaced as warnings via ui rather
// than propagated, so a transient image-pull failure does not abort the
// otherwise-completed binary update. The caller is responsible for
// surfacing the final state.
func ApplyUpdate(release *Release, ref string) error {
	if release == nil {
		return fmt.Errorf("nil release")
	}

	ui.Info("Syncing configuration files...")
	// Pass release through so SyncConfigFiles can verify against the
	// release-pinned manifest when we're tracking a tag. Branch-mode
	// (ref differs from release.TagName) gets nil so verification is
	// skipped with a warning instead of failing.
	syncRelease := release
	if ref != release.TagName && ref != strings.TrimPrefix(release.TagName, "v") {
		syncRelease = nil
	}
	if err := SyncConfigFiles(ref, syncRelease); err != nil {
		ui.Warning("Config sync: " + err.Error())
	}

	c := compose.New()
	targetVersion := strings.TrimPrefix(release.TagName, "v")
	ui.Info("Pulling Docker images (" + targetVersion + ")...")
	if err := c.Pull(targetVersion); err != nil {
		ui.Warning("Image pull: " + err.Error())
	}

	if err := SelfUpdate(release); err != nil {
		return fmt.Errorf("binary update: %w", err)
	}
	if err := WriteVersion(release.TagName); err != nil {
		ui.Warning("Write version stamp: " + err.Error())
	}
	return nil
}

// PromptIfUpdateAvailable presents an interactive y/n confirmation when a
// newer release exists. On approval, applies the update and re-execs the
// running launcher with the freshly installed binary so the rest of the
// caller's flow runs against the new version (matches the Claude Code /
// Codex CLI behavior of "update applied, restarting").
//
// Returns “true“ only when the user approved AND ApplyUpdate succeeded
// AND re-exec was issued. On POSIX the re-exec replaces the process via
// “syscall.Exec“, so a true return is effectively unreachable; the
// helper still returns the value for tests and Windows callers, where
// re-exec spawns a child + “os.Exit“ from the parent.
//
// Skips silently (returns false, nil) when:
//   - “currentVersion“ is empty / "dev" — local build, no published release to track.
//   - “FetchLatestRelease“ fails — offline or GitHub unavailable.
//   - the latest release is not newer than “currentVersion“.
//   - stdin is not a TTY — CI / piped invocations fall back to
//     “NotifyIfUpdateAvailable“ so the user still sees the notice.
func PromptIfUpdateAvailable(currentVersion string) (bool, error) {
	if currentVersion == "" || currentVersion == "dev" {
		return false, nil
	}
	if !isInteractiveStdin() {
		NotifyIfUpdateAvailable(currentVersion)
		return false, nil
	}

	release, err := FetchLatestRelease()
	if err != nil {
		return false, nil // Silent skip — startup must not depend on GitHub.
	}
	if !CompareVersions(currentVersion, release.TagName) {
		return false, nil
	}

	ui.Info(fmt.Sprintf(
		"Update available: %s → %s",
		displayVersion(currentVersion),
		release.TagName,
	))

	var confirmed bool
	if err := huh.NewConfirm().
		Title(fmt.Sprintf("Install %s now?", release.TagName)).
		Description(
			"Updates the launcher binary, docker-compose config, and pulls\n" +
				"the matching Docker images. Decepticon will restart with\n" +
				"the new version once the update finishes.",
		).
		Affirmative("Yes, update").
		Negative("Skip").
		Value(&confirmed).
		Run(); err != nil {
		// Prompt failure (e.g. tty closed mid-render) — fall through to
		// the passive notice rather than crashing the launch.
		ui.Warning("Update prompt failed: " + err.Error())
		return false, nil
	}
	if !confirmed {
		ui.DimText(
			"Continuing with " + displayVersion(currentVersion) +
				". Run `decepticon update` later to upgrade.",
		)
		return false, nil
	}

	return applyAndReexec(release, currentVersion)
}

// isInteractiveStdin returns true when the launcher's stdin is connected
// to a real terminal. Piped / redirected stdin (CI, log shippers,
// supervisor pipelines) returns false so the launch flow falls back to
// the passive update notice instead of blocking on a prompt that nobody
// can answer.
func isInteractiveStdin() bool {
	return term.IsTerminal(int(os.Stdin.Fd()))
}

func displayVersion(version string) string {
	version = strings.TrimSpace(version)
	if version == "" || version == "dev" || strings.HasPrefix(version, "v") {
		return version
	}
	return "v" + version
}

// resolveUpdateRef picks the git ref for SyncConfigFiles: an explicit
// DECEPTICON_BRANCH override in .env, otherwise the release tag.
func resolveUpdateRef(release *Release) string {
	ref := release.TagName
	if config.EnvExists() {
		if env, lerr := config.LoadEnv(config.EnvPath()); lerr == nil {
			if branch := strings.TrimSpace(env["DECEPTICON_BRANCH"]); branch != "" {
				ref = branch
			}
		}
	}
	return ref
}

// applyAndReexec runs the full upgrade (config sync + image pull + binary
// self-update + .version stamp) then re-execs into the freshly installed
// binary. Shared by the interactive prompt (after confirmation) and the
// unattended AUTO_UPDATE path so both behave identically.
func applyAndReexec(release *Release, currentVersion string) (bool, error) {
	if err := ApplyUpdate(release, resolveUpdateRef(release)); err != nil {
		ui.Warning("Update failed: " + err.Error())
		ui.DimText("Continuing with " + displayVersion(currentVersion) + ".")
		return false, nil
	}
	ui.Success("Update complete — restarting with " + release.TagName + "...")
	if err := reexecSelf(); err != nil {
		// Re-exec failed: tell the user to restart manually rather than
		// silently keep running the old in-memory image.
		ui.Warning("Re-exec failed: " + err.Error())
		ui.DimText("Run `decepticon` again to use the new version.")
		os.Exit(0)
	}
	// POSIX exec replaces the process — control never reaches here. The
	// Windows path inside reexecSelf calls os.Exit after spawning the
	// child, so this is also unreachable on Windows. Kept for symmetry.
	return true, nil
}

// AutoUpdateIfAvailable applies a newer release WITHOUT prompting. Wired to
// the AUTO_UPDATE=true launch path for fully-unattended self-update (servers,
// CI runners, kiosk deployments). Skips silently on dev builds, when offline,
// or when already current — a self-update must never block or break a launch.
func AutoUpdateIfAvailable(currentVersion string) (bool, error) {
	if currentVersion == "" || currentVersion == "dev" {
		return false, nil
	}
	release, err := FetchLatestRelease()
	if err != nil {
		return false, nil // offline / GitHub down — never block launch
	}
	if !CompareVersions(currentVersion, release.TagName) {
		return false, nil
	}
	ui.Info(fmt.Sprintf(
		"Auto-updating: %s → %s (AUTO_UPDATE enabled)",
		displayVersion(currentVersion),
		release.TagName,
	))
	return applyAndReexec(release, currentVersion)
}
