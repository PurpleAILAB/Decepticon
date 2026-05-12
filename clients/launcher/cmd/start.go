package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/engagement"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/health"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/platform"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/updater"
	"github.com/spf13/cobra"
)

// Indirected so tests can swap WSL detection without touching the
// real /proc/version or /etc/resolv.conf on the host they run on.
var (
	isWSLFn     = platform.IsWSL
	wslHostIPFn = platform.WSLHostIP
)

var startCmd = &cobra.Command{
	Use:   "start",
	Short: "Start Decepticon services and launch the CLI",
	RunE:  runStart,
}

func init() {
	rootCmd.AddCommand(startCmd)

	// Make start the default command when no subcommand given
	rootCmd.RunE = func(cmd *cobra.Command, args []string) error {
		// If no subcommand, run start
		return runStart(cmd, args)
	}
}

func runStart(cmd *cobra.Command, args []string) error {
	// 1. Check .env exists
	if !config.EnvExists() {
		ui.Warning("No configuration found. Running setup wizard...")
		fmt.Println()
		if err := runOnboard(cmd, nil); err != nil {
			return err
		}
		fmt.Println()
	}

	// 2. Load and validate .env
	env, err := config.LoadEnv(config.EnvPath())
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}
	if err := config.ValidateAuth(env); err != nil {
		return err
	}

	// Warn — don't block — if Ollama is selected but the URL doesn't
	// reach a running server. We translate ``host.docker.internal`` to
	// ``localhost`` for the host-side probe; from inside the litellm
	// container the original URL is what gets used at runtime.
	probeOllamaIfSelected(env)

	// 2.3. Ensure config files exist (docker-compose.yml, litellm.yaml, workspace)
	home := config.DecepticonHome()
	composePath := filepath.Join(home, "docker-compose.yml")
	if _, err := os.Stat(composePath); os.IsNotExist(err) {
		// Use installed version tag; fall back to branch for dev builds
		ref := "v" + version
		if version == "dev" || version == "" {
			ref = config.Get(env, "DECEPTICON_BRANCH", "main")
		}
		ui.Info("Downloading configuration files...")
		if err := updater.SyncConfigFiles(ref); err != nil {
			return fmt.Errorf("sync config: %w", err)
		}
	}

	// Ensure workspace directory exists
	_ = os.MkdirAll(filepath.Join(home, "workspace"), 0o755)

	// Ensure DECEPTICON_HOME is set in .env (Docker Compose needs absolute path)
	if config.Get(env, "DECEPTICON_HOME", "") == "" {
		env["DECEPTICON_HOME"] = home
		if err := config.AppendEnvLine(config.EnvPath(), "DECEPTICON_HOME", home); err != nil {
			ui.Warning("Could not set DECEPTICON_HOME in .env: " + err.Error())
		}
	}

	// 2.6. Set CLAUDE_CREDENTIALS_VOLUME for conditional mount in docker-compose.
	// When the credentials file exists, mount it into litellm. Otherwise mount
	// /dev/null so docker doesn't create it as a directory.
	credsPath := filepath.Join(os.Getenv("HOME"), ".claude", ".credentials.json")
	if _, statErr := os.Stat(credsPath); statErr == nil {
		_ = os.Setenv("CLAUDE_CREDENTIALS_VOLUME", credsPath)
	} else {
		_ = os.Setenv("CLAUDE_CREDENTIALS_VOLUME", "/dev/null")
	}

	// Same pattern for the Codex CLI credential store at ~/.codex/auth.json.
	// The new auth/ ChatGPT handler reads (and writes) this file directly so
	// a host-side `codex login` flows into the container without a rebuild.
	codexAuthPath := filepath.Join(os.Getenv("HOME"), ".codex", "auth.json")
	if _, statErr := os.Stat(codexAuthPath); statErr == nil {
		_ = os.Setenv("CODEX_AUTH_VOLUME", codexAuthPath)
	} else {
		_ = os.Setenv("CODEX_AUTH_VOLUME", "/dev/null")
	}

	// 2.5. Update prompt. When a newer release is available and stdin is
	// a TTY, ask the operator interactively whether to apply it. On
	// confirmation the launcher applies the update (config sync + image
	// pull + binary replace) and re-execs itself so the rest of this
	// ``start`` flow runs against the just-installed version — matches
	// the Claude Code / Codex CLI "update available, restarting" UX.
	// Non-interactive shells (CI, piped) fall back to the passive notice
	// path inside ``PromptIfUpdateAvailable``.
	if _, err := updater.PromptIfUpdateAvailable(version); err != nil {
		// Non-fatal — surface as a warning and continue with the
		// current launcher rather than aborting the start.
		ui.Warning("Update check: " + err.Error())
	}

	// 3. Engagement picker — must run BEFORE compose Up so the sandbox
	// container starts with /workspace bound to the chosen engagement
	// directory. Without this, the operator would briefly see the whole
	// workspace through the sandbox before any picking happens.
	fmt.Println()
	choice, err := engagement.Select(home)
	if err != nil {
		return err
	}
	// Export the bind path. composeEnv() forwards os.Environ(), so docker
	// compose interpolates ${DECEPTICON_ENGAGEMENT_WORKSPACE} from this var.
	if err := os.Setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", choice.WorkspacePath); err != nil {
		return fmt.Errorf("set engagement workspace env: %w", err)
	}

	// Stage any source_code targets from the RoE into <workspace>/src/ so the
	// analyst sandbox can read them at /workspace/src. Soundwave writes the RoE
	// after the interview (which happens inside the CLI), so we poll in the
	// background — by the time the operator finishes reviewing and approving the
	// OPPLAN the copy is already done.
	go stageSourceTargets(choice.WorkspacePath)

	// 4. Start services
	c := compose.New()

	ui.Info("Starting Decepticon services...")
	if err := c.Up(compose.Profiles.CLI); err != nil {
		return fmt.Errorf("start services: %w", err)
	}

	// 5. Health checks
	if err := health.WaitForServices(env); err != nil {
		return err
	}

	// 6. Launch CLI
	fmt.Println()
	ui.Info("Launching Decepticon CLI...")

	cliEnv := map[string]string{
		"DECEPTICON_VERSION":      version,
		"DECEPTICON_ASSISTANT_ID": choice.AssistantID,
		"DECEPTICON_ENGAGEMENT":   choice.Engagement,
	}
	if port := config.Get(env, "WEB_PORT", "3000"); port != "" {
		cliEnv["WEB_PORT"] = port
	}

	// Pass through terminal. Services are intentionally left running on CLI exit
	// so re-entry is fast (cold start is ~75s); use 'decepticon stop' to shut
	// the stack down.
	if err := c.RunInteractive(
		[]string{compose.Profiles.CLI},
		"cli",
		cliEnv,
	); err != nil {
		ui.Warning("CLI exited with error — if services just started, try 'decepticon' again.")
		ui.DimText("Run 'decepticon logs litellm' or 'decepticon logs langgraph' to debug.")
		return nil
	}

	ui.DimText("CLI exited. Services kept running — run 'decepticon stop' to shut down.")
	return nil
}

// stageSourceTargets polls for the RoE written by Soundwave during the CLI
// interview and copies any source_code targets into <workspace>/src/ on the
// host filesystem. Because /workspace is bind-mounted to the engagement
// workspace directory, the analyst sandbox sees the source at /workspace/src
// immediately after the copy without any container restart.
//
// Destination layout:
//   - 1 source target  → <workspace>/src        (flat; matches analyst prompts)
//   - N source targets → <workspace>/src/<name> (per-target subdirs; no silent merging)
//
// Each destination is replaced atomically via a staging directory so a crashed
// or re-run engagement never leaves a hybrid tree from two different runs.
//
// The poll runs for up to two hours so it covers slow Soundwave interviews.
// Failures are surfaced as warnings and never block the engagement.
func stageSourceTargets(workspacePath string) {
	roePath := filepath.Join(workspacePath, "plan", "roe.json")

	// Wait for Soundwave to write the RoE (up to 2 hours, 10s polling).
	const (
		maxAttempts  = 720
		pollInterval = 10 * time.Second
	)
	for i := range maxAttempts {
		if _, err := os.Stat(roePath); err == nil {
			break
		}
		if i == maxAttempts-1 {
			return // timed out — no RoE appeared
		}
		time.Sleep(pollInterval)
	}

	data, err := os.ReadFile(roePath)
	if err != nil {
		ui.Warning("source staging: could not read roe.json: " + err.Error())
		return
	}

	// The RoE JSON uses in_scope_targets (Soundwave's generated key) or
	// in_scope (schema field name) — handle both to be forward-compatible.
	var roe struct {
		InScopeTargets []struct {
			Target string `json:"target"`
			Type   string `json:"type"`
		} `json:"in_scope_targets"`
		InScope []struct {
			Target string `json:"target"`
			Type   string `json:"type"`
		} `json:"in_scope"`
	}
	if err := json.Unmarshal(data, &roe); err != nil {
		ui.Warning("source staging: could not parse roe.json: " + err.Error())
		return
	}

	// Collect valid source_code / local-path entries, validating each path
	// exists on the host before committing to any copy work.
	combined := make([]struct {
		Target string `json:"target"`
		Type   string `json:"type"`
	}, 0, len(roe.InScopeTargets)+len(roe.InScope))
	combined = append(combined, roe.InScopeTargets...)
	combined = append(combined, roe.InScope...)

	var sourcePaths []string
	for _, entry := range combined {
		if entry.Type != "source_code" && entry.Type != "local-path" {
			continue
		}
		if _, err := os.Stat(entry.Target); err != nil {
			ui.Warning(fmt.Sprintf("source staging: path %q not found on host — skipping", entry.Target))
			continue
		}
		sourcePaths = append(sourcePaths, entry.Target)
	}

	if len(sourcePaths) == 0 {
		return
	}

	for i, srcPath := range sourcePaths {
		// Determine destination: flat for a single target, per-name subdir for many.
		var dstPath string
		if len(sourcePaths) == 1 {
			dstPath = filepath.Join(workspacePath, "src")
		} else {
			name := sanitizeDirName(filepath.Base(srcPath))
			if name == "" {
				name = fmt.Sprintf("target-%d", i+1)
			}
			dstPath = filepath.Join(workspacePath, "src", name)
		}

		ui.Info(fmt.Sprintf("Staging source %q → workspace/src (white-box analysis)...", srcPath))

		// Atomic replace: copy into <dst>.staging, then rename into place.
		// Both paths live inside workspacePath so the rename stays on one
		// filesystem and is atomic on Linux and macOS.
		stagingPath := dstPath + ".staging"
		_ = os.RemoveAll(stagingPath) // clean up any prior failed attempt

		if err := copyDirTree(srcPath, stagingPath); err != nil {
			ui.Warning(fmt.Sprintf("source staging: copy %q failed: %s — cleaning up", srcPath, err.Error()))
			_ = os.RemoveAll(stagingPath)
			continue
		}

		_ = os.RemoveAll(dstPath) // remove previous version before the rename
		if err := os.Rename(stagingPath, dstPath); err != nil {
			ui.Warning(fmt.Sprintf("source staging: rename failed for %q: %s", srcPath, err.Error()))
			_ = os.RemoveAll(stagingPath)
			continue
		}

		ui.DimText("Source staged at /workspace/src — analyst will find it there.")
	}
}

// sanitizeDirName replaces characters that are unsafe in directory names with
// underscores so per-target subdir names are always valid on all platforms.
func sanitizeDirName(name string) string {
	var b strings.Builder
	for _, r := range name {
		switch r {
		case '/', '\\', ':', '*', '?', '"', '<', '>', '|':
			b.WriteRune('_')
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

// copyDirTree recursively copies src into dst, creating dst if it does not
// exist. Symlinks are explicitly skipped — os.Open follows symlinks, so
// copying them could pull files from outside the intended source tree
// (e.g. a repo symlink pointing at ~/.ssh/id_rsa would land in the sandbox).
// Unreadable files are skipped with a warning rather than aborting the copy.
func copyDirTree(src, dst string) error {
	return filepath.WalkDir(src, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			ui.Warning(fmt.Sprintf("source staging: skipping %q: %s", path, err.Error()))
			return nil
		}
		// Skip symlinks — do not dereference them into the sandbox.
		if d.Type()&fs.ModeSymlink != 0 {
			ui.Warning(fmt.Sprintf("source staging: skipping symlink %q", path))
			return nil
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		return copyFilePath(path, target)
	})
}

// copyFilePath copies a single regular file from src to dst, creating parent
// directories as needed.
func copyFilePath(src, dst string) error {
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

// probeOllamaIfSelected does a best-effort GET on /api/tags to verify the
// user's Ollama server is reachable when `ollama_local` is configured.
// Failures don't block startup — the user might be about to launch
// Ollama, or running on an unusual setup we can't introspect. We just
// surface a hint so they aren't surprised by a 'model not found' on the
// first agent prompt.
//
// On WSL2 the probe walks several candidate hosts because there's no
// single "the host" address: Docker Desktop installs may have
// host.docker.internal in /etc/hosts; native-WSL Docker installs need
// the Windows host IP from /etc/resolv.conf; an Ollama running inside
// the WSL distro itself sits on 127.0.0.1. Whichever returns 2xx wins.
func probeOllamaIfSelected(env map[string]string) {
	priority := strings.ToLower(env["DECEPTICON_AUTH_PRIORITY"])
	hasOllama := strings.Contains(","+priority+",", ",ollama_local,")
	base := strings.TrimSpace(env["OLLAMA_API_BASE"])
	if !hasOllama && base == "" {
		return
	}
	if base == "" {
		ui.Warning("ollama_local selected but OLLAMA_API_BASE is empty — skipping reachability probe.")
		return
	}

	candidates := candidateProbeURLs(base)
	client := &http.Client{Timeout: 2 * time.Second}
	var lastStatus int
	for _, candidate := range candidates {
		resp, err := client.Get(candidate + "/api/tags")
		if err != nil {
			continue
		}
		status := resp.StatusCode
		resp.Body.Close()
		if status < 400 {
			ui.DimText(fmt.Sprintf("Ollama reachable at %s.", base))
			return
		}
		lastStatus = status
	}

	if lastStatus != 0 {
		ui.Warning(fmt.Sprintf(
			"Ollama responded with %d at %s — verify the URL is correct.",
			lastStatus, base,
		))
		return
	}
	ui.Warning(fmt.Sprintf(
		"Ollama not reachable at %s (host-side probe). "+
			"Start it with 'ollama serve' or check OLLAMA_API_BASE.",
		base,
	))
}

// candidateProbeURLs returns the URLs the launcher should probe to
// verify host-side Ollama reachability. The returned list is ordered
// best-first so the loop short-circuits on the most likely candidate.
//
// For URLs that don't reference `host.docker.internal` the list is
// just the URL itself — the user wired up an explicit address (real
// IP, DNS name) and we trust it.
//
// For `host.docker.internal` the resolution depends on platform:
//
//   - Always try the URL verbatim first. Docker Desktop on macOS,
//     Windows, and WSL2 typically populates /etc/hosts with this name.
//   - On WSL, also try the Windows host IP found in /etc/resolv.conf.
//     Native-WSL Docker installs (no Docker Desktop) don't get the
//     hosts entry, but the Windows host is always the WSL2 default
//     nameserver, so this catches the "Ollama on Windows" case.
//   - Always fall back to 127.0.0.1. Native Linux Docker reaches the
//     host loopback via the `extra_hosts: host-gateway` mapping,
//     which on the host is just localhost. On WSL this also catches
//     the "Ollama running inside the WSL distro" case.
func candidateProbeURLs(raw string) []string {
	u, err := url.Parse(raw)
	if err != nil {
		return []string{raw}
	}
	host, port, splitErr := net.SplitHostPort(u.Host)
	if splitErr != nil {
		host = u.Host
		port = ""
	}
	if host != "host.docker.internal" {
		return []string{raw}
	}

	candidates := []string{raw}
	seen := map[string]struct{}{raw: {}}
	add := func(replacement string) {
		v := *u
		if port == "" {
			v.Host = replacement
		} else {
			v.Host = net.JoinHostPort(replacement, port)
		}
		s := v.String()
		if _, dup := seen[s]; dup {
			return
		}
		seen[s] = struct{}{}
		candidates = append(candidates, s)
	}

	if isWSLFn() {
		if hostIP := wslHostIPFn(); hostIP != "" {
			add(hostIP)
		}
	}
	add("127.0.0.1")
	return candidates
}
