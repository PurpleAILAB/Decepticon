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
	"strconv"
	"strings"
	"syscall"
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

// Indirected so staging tests can inject fake filesystem ops and fast timers.
var (
	readFileFn      = os.ReadFile
	statFn          = os.Stat
	nowFn           = time.Now
	pollIntervalVar = 10 * time.Second
	maxAttemptsVar  = 720
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

	// Warn early if source staging is disabled so the operator knows before
	// they start the planning interview, not after Soundwave finishes.
	if os.Getenv("DECEPTICON_SOURCE_ROOT") == "" {
		ui.DimText("Note: DECEPTICON_SOURCE_ROOT is not set — source_code RoE targets will be skipped. " +
			"Set it to your project root to enable source staging " +
			"(e.g. export DECEPTICON_SOURCE_ROOT=$HOME/projects).")
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

	// One-time migration: for engagements completed before the .bundle_complete
	// marker was introduced, write the marker now so the staging goroutine isn't
	// stranded waiting for a file that Soundwave already wrote in a prior session.
	migrateEngagementMarker(choice.WorkspacePath)

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

// stagingBudget tracks cumulative size and maximum depth constraints when
// walking a source tree. Both fields are mutable by copyDirTree's walk closure.
type stagingBudget struct {
	bytesLeft int64
	maxDepth  int
}

// stagingStatus values written to <workspace>/.decepticon/staging-status.json.
const (
	stagingPending    = "pending"
	stagingInProgress = "in_progress"
	stagingStaged     = "staged"
	stagingFailed     = "failed"
	stagingSkipped    = "skipped"
	stagingDisabled   = "disabled"
	// Backup retention for pruneOldStagingArtifacts.
	stagingBackupRetention = 7 * 24 * time.Hour
)

// writeStagingStatus atomically writes a JSON status record to
// <workspace>/.decepticon/staging-status.json.
func writeStagingStatus(workspacePath, state string, sources []string, stagingErr error) {
	dir := filepath.Join(workspacePath, ".decepticon")
	_ = os.MkdirAll(dir, 0o755)
	type statusDoc struct {
		State     string   `json:"state"`
		Sources   []string `json:"sources,omitempty"`
		Error     string   `json:"error,omitempty"`
		UpdatedAt string   `json:"updated_at"`
	}
	doc := statusDoc{
		State:     state,
		Sources:   sources,
		UpdatedAt: nowFn().UTC().Format(time.RFC3339),
	}
	if stagingErr != nil {
		doc.Error = stagingErr.Error()
	}
	data, _ := json.Marshal(doc)
	dst := filepath.Join(dir, "staging-status.json")
	tmp, err := os.CreateTemp(dir, "staging-status.*.json")
	if err != nil {
		return
	}
	tmpPath := tmp.Name()
	_, werr := tmp.Write(data)
	syncErr := tmp.Sync()
	tmp.Close()
	if werr != nil || syncErr != nil {
		_ = os.Remove(tmpPath)
		return
	}
	_ = os.Rename(tmpPath, dst)
}

// pruneOldStagingArtifacts removes src.prev-* and src.new-* entries in
// stagingBase whose modtime is older than stagingBackupRetention and whose
// name does not match currentRunID.
func pruneOldStagingArtifacts(stagingBase, currentRunID string) {
	entries, err := os.ReadDir(stagingBase)
	if err != nil {
		return
	}
	cutoff := nowFn().Add(-stagingBackupRetention)
	for _, e := range entries {
		name := e.Name()
		if !strings.HasPrefix(name, "src.prev-") && !strings.HasPrefix(name, "src.new-") {
			continue
		}
		if strings.HasSuffix(name, currentRunID) {
			continue
		}
		info, err := e.Info()
		if err != nil || !info.ModTime().Before(cutoff) {
			continue
		}
		_ = os.RemoveAll(filepath.Join(stagingBase, name))
	}
}

// atomicWriteMarker writes data to path using a temp file + rename, sharing
// the same directory as path so both are on the same filesystem.
func atomicWriteMarker(path string, data []byte) error {
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".marker.*.tmp")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	_, werr := tmp.Write(data)
	syncErr := tmp.Sync()
	tmp.Close()
	if werr != nil || syncErr != nil {
		_ = os.Remove(tmpPath)
		if werr != nil {
			return werr
		}
		return syncErr
	}
	return os.Rename(tmpPath, path)
}

// migrateEngagementMarker writes a plan/.bundle_complete marker for engagements
// that were completed before this marker was introduced (pre-upgrade). It only
// fires when all three plan docs exist and no marker is present, and silently
// skips when any condition is unmet so it never interferes with in-progress
// Soundwave interviews.
//
// This is called synchronously from runStart before the staging goroutine
// spawns so the goroutine can always assume the marker exists if the
// engagement was already complete at launch time.
func migrateEngagementMarker(workspacePath string) {
	abs, err := filepath.Abs(workspacePath)
	if err != nil {
		return
	}
	planDir := filepath.Join(abs, "plan")
	markerPath := filepath.Join(planDir, ".bundle_complete")
	if _, err := statFn(markerPath); err == nil {
		return // marker already present — nothing to do
	}
	planDocs := []string{
		filepath.Join(planDir, "roe.json"),
		filepath.Join(planDir, "conops.json"),
		filepath.Join(planDir, "deconfliction.json"),
	}
	for _, f := range planDocs {
		if _, err := statFn(f); err != nil {
			return // incomplete bundle — Soundwave is still running
		}
	}
	data, err := readFileFn(filepath.Join(planDir, "roe.json"))
	if err != nil {
		return
	}
	var tmp interface{}
	if json.Unmarshal(data, &tmp) != nil {
		return // malformed roe.json — don't migrate
	}
	markerBody, _ := json.Marshal(map[string]interface{}{
		"completed_at":   nowFn().UTC().Format(time.RFC3339),
		"schema_version": 1,
		"migrated":       true,
	})
	if err := atomicWriteMarker(markerPath, markerBody); err == nil {
		ui.DimText("source staging: wrote .bundle_complete marker for existing engagement (one-time migration).")
	}
}

// stageSourceTargets waits for complete_engagement_planning to write the
// plan/.bundle_complete marker, then copies source_code targets from the RoE
// into <workspace>/src/ so the analyst sandbox has them at /workspace/src.
//
// Readiness gate: poll for plan/.bundle_complete AND verify marker mtime ≥
// each of roe.json / conops.json / deconfliction.json. This prevents staging
// from a stale marker left over from a prior engagement or a partial replan.
//
// Destination layout:
//   - 1 source target  → <workspace>/src        (flat; matches analyst prompts)
//   - N source targets → <workspace>/src/<name> (per-target subdirs; no silent merging)
//
// Requires DECEPTICON_SOURCE_ROOT to be set to an absolute path; staging is
// disabled if the variable is absent so arbitrary host paths cannot be staged
// from a prompt-injected RoE.
//
// The poll runs for up to two hours so it covers slow Soundwave interviews.
// Failures are surfaced as warnings and never block the engagement.
func stageSourceTargets(workspacePath string) {
	// Absolutize the workspace path before any path arithmetic so that
	// stagingParent and stagingBase are always on a known absolute root.
	var absErr error
	workspacePath, absErr = filepath.Abs(workspacePath)
	if absErr != nil {
		ui.Warning("source staging: could not resolve workspace path: " + absErr.Error())
		return
	}
	base := filepath.Base(workspacePath)
	if base == "" || base == "." || base == ".." {
		ui.Warning("source staging: workspace path has unsafe basename — skipping")
		return
	}

	// Deferred finalizer: guarantees staging-status.json always reaches a
	// terminal state for normal returns and panics that unwind defers.
	// Hard process exits (SIGKILL, OOM) may leave a transitional state on
	// disk; callers should treat "pending"/"in_progress" as stale.
	terminalState := stagingSkipped
	var stagingFinalErr error
	var stagedSources []string
	writeStagingStatus(workspacePath, stagingPending, nil, nil)
	defer func() {
		writeStagingStatus(workspacePath, terminalState, stagedSources, stagingFinalErr)
	}()

	// Fail closed early: if DECEPTICON_SOURCE_ROOT is unset, disable staging
	// and record the "disabled" terminal state so downstream tooling can
	// distinguish "nothing to stage" from "env var missing".
	rawRoot := os.Getenv("DECEPTICON_SOURCE_ROOT")
	if rawRoot == "" {
		ui.Warning("source staging: DECEPTICON_SOURCE_ROOT is not set — staging disabled. " +
			"Set it to the project root to allow source staging " +
			"(e.g. export DECEPTICON_SOURCE_ROOT=$HOME/projects).")
		terminalState = stagingDisabled
		return
	}

	planDir := filepath.Join(workspacePath, "plan")
	markerPath := filepath.Join(planDir, ".bundle_complete")
	roePath := filepath.Join(planDir, "roe.json")
	planDocs := []string{roePath,
		filepath.Join(planDir, "conops.json"),
		filepath.Join(planDir, "deconfliction.json"),
	}

	// Poll for .bundle_complete AND marker mtime ≥ all doc mtimes.
	// The mtime check prevents staging from a stale marker left by a prior
	// run when Soundwave has since re-written the plan docs (replan scenario).
	ready := false
	for i := range maxAttemptsVar {
		markerInfo, err := statFn(markerPath)
		if err != nil {
			if i == maxAttemptsVar-1 {
				ui.Warning("source staging: timed out waiting for plan/.bundle_complete — staging skipped.")
				stagingFinalErr = fmt.Errorf("marker timeout after %d attempts", maxAttemptsVar)
				terminalState = stagingFailed
				return
			}
			time.Sleep(pollIntervalVar)
			continue
		}
		// Verify marker mtime ≥ every plan doc to catch partial replans.
		consistent := true
		for _, doc := range planDocs {
			docInfo, statErr := statFn(doc)
			if statErr != nil {
				consistent = false
				break
			}
			if docInfo.ModTime().After(markerInfo.ModTime()) {
				consistent = false
				break
			}
		}
		if consistent {
			ready = true
			break
		}
		if i == maxAttemptsVar-1 {
			ui.Warning("source staging: timed out waiting for consistent .bundle_complete — staging skipped.")
			stagingFinalErr = fmt.Errorf("stale marker timeout after %d attempts", maxAttemptsVar)
			terminalState = stagingFailed
			return
		}
		time.Sleep(pollIntervalVar)
	}
	if !ready {
		terminalState = stagingFailed
		return
	}

	// Read and parse roe.json with bounded retry to tolerate slow fsync
	// visibility on network filesystems.
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
	const parseRetries = 5
	for attempt := range parseRetries {
		data, err := readFileFn(roePath)
		if err != nil {
			if attempt == parseRetries-1 {
				ui.Warning("source staging: could not read roe.json: " + err.Error())
				stagingFinalErr = err
				terminalState = stagingFailed
				return
			}
			time.Sleep(time.Second)
			continue
		}
		if err := json.Unmarshal(data, &roe); err != nil {
			if attempt == parseRetries-1 {
				ui.Warning("source staging: could not parse roe.json: " + err.Error())
				stagingFinalErr = err
				terminalState = stagingFailed
				return
			}
			time.Sleep(time.Second)
			continue
		}
		break
	}

	// Merge in_scope (canonical) and in_scope_targets (backward-compat;
	// primary is in_scope; in_scope_targets is accepted for
	// orchestration-skill-emitted RoE).
	combined := make([]struct {
		Target string `json:"target"`
		Type   string `json:"type"`
	}, 0, len(roe.InScopeTargets)+len(roe.InScope))
	combined = append(combined, roe.InScope...)
	combined = append(combined, roe.InScopeTargets...)

	// Resolve allowedRoot to a real, symlink-free absolute path.
	absRoot, absRootErr := filepath.Abs(rawRoot)
	if absRootErr != nil {
		ui.Warning("source staging: could not make DECEPTICON_SOURCE_ROOT absolute: " + absRootErr.Error())
		stagingFinalErr = absRootErr
		terminalState = stagingFailed
		return
	}
	allowedRoot, evalRootErr := filepath.EvalSymlinks(absRoot)
	if evalRootErr != nil {
		ui.Warning("source staging: could not resolve DECEPTICON_SOURCE_ROOT symlinks: " + evalRootErr.Error())
		stagingFinalErr = evalRootErr
		terminalState = stagingFailed
		return
	}

	// Warn specifically if RoE has source_code entries but env var is unset.
	// (We already checked rawRoot != "" above, so this branch warns when there
	// are entries that can't be staged due to a missing root — not reachable
	// in the current flow, but guard is left for clarity.)

	var sourcePaths []string
	seenSourceEntries := 0
	for _, entry := range combined {
		if entry.Type != "source_code" && entry.Type != "local-path" && entry.Type != "local_path" {
			continue
		}
		seenSourceEntries++
		absTarget, absErr := filepath.Abs(entry.Target)
		if absErr != nil {
			ui.Warning(fmt.Sprintf("source staging: cannot make path %q absolute — skipping", entry.Target))
			continue
		}
		if _, statErr := statFn(absTarget); statErr != nil {
			ui.Warning(fmt.Sprintf("source staging: path %q not found on host — skipping", absTarget))
			continue
		}
		realTarget, evalErr := filepath.EvalSymlinks(absTarget)
		if evalErr != nil {
			ui.Warning(fmt.Sprintf("source staging: cannot resolve symlinks in %q — skipping", absTarget))
			continue
		}
		if realTarget != allowedRoot && !strings.HasPrefix(realTarget, allowedRoot+string(filepath.Separator)) {
			ui.Warning(fmt.Sprintf(
				"source staging: path %q (resolves to %q) is outside allowed root %q — skipping "+
					"(set DECEPTICON_SOURCE_ROOT to allow additional roots)",
				entry.Target, realTarget, allowedRoot,
			))
			continue
		}
		ui.DimText(fmt.Sprintf("source staging: authorized %q (within %q)", realTarget, allowedRoot))
		sourcePaths = append(sourcePaths, realTarget)
	}

	if len(sourcePaths) == 0 {
		if seenSourceEntries > 0 {
			// Source targets were declared but every one was rejected (missing, outside
			// root, unresolvable). This is a real failure, not an absence of intent.
			stagingFinalErr = fmt.Errorf(
				"all %d source_code target(s) were rejected during validation (missing path, outside DECEPTICON_SOURCE_ROOT, or unresolvable symlink)",
				seenSourceEntries,
			)
			terminalState = stagingFailed
		}
		// If seenSourceEntries == 0, terminalState stays "skipped" (no source targets in RoE).
		return
	}

	// stagingBase lives alongside (not inside) workspacePath so the sandbox
	// bind-mount never exposes staging artifacts to the analyst container.
	stagingParent := filepath.Dir(workspacePath)
	stagingBase := filepath.Join(stagingParent, ".src_staging_"+base)
	if err := os.MkdirAll(stagingBase, 0o755); err != nil {
		ui.Warning("source staging: could not create staging dir: " + err.Error())
		stagingFinalErr = err
		terminalState = stagingFailed
		return
	}

	runID := fmt.Sprintf("%x", nowFn().UnixNano())
	pruneOldStagingArtifacts(stagingBase, runID)

	dstPath := filepath.Join(workspacePath, "src")
	newSrcPath := filepath.Join(stagingBase, "src.new-"+runID)
	prevPath := filepath.Join(stagingBase, "src.prev-"+runID)
	defer func() { _ = os.RemoveAll(newSrcPath) }()

	writeStagingStatus(workspacePath, stagingInProgress, nil, nil)

	// Read size/depth budget from env vars; fall back to defaults.
	maxBytes := int64(2 << 30) // 2 GiB default
	if envBytes := os.Getenv("DECEPTICON_MAX_STAGED_BYTES"); envBytes != "" {
		if parsed, err := strconv.ParseInt(envBytes, 10, 64); err == nil && parsed > 0 {
			maxBytes = parsed
		}
	}
	maxDepth := 32
	if envDepth := os.Getenv("DECEPTICON_MAX_STAGED_DEPTH"); envDepth != "" {
		if parsed, err := strconv.Atoi(envDepth); err == nil && parsed > 0 {
			maxDepth = parsed
		}
	}

	budget := &stagingBudget{bytesLeft: maxBytes, maxDepth: maxDepth}
	seenNames := make(map[string]bool)
	for i, srcPath := range sourcePaths {
		var targetPath string
		if len(sourcePaths) == 1 {
			targetPath = newSrcPath
		} else {
			name := sanitizeDirName(filepath.Base(srcPath))
			if name == "" {
				name = fmt.Sprintf("target-%d", i+1)
			}
			candidate := name
			for j := 2; seenNames[candidate]; j++ {
				candidate = fmt.Sprintf("%s-%d", name, j)
			}
			seenNames[candidate] = true
			targetPath = filepath.Join(newSrcPath, candidate)
		}
		ui.Info(fmt.Sprintf("Staging source %q → workspace/src (white-box analysis)...", srcPath))
		if err := copyDirTree(srcPath, targetPath, budget); err != nil {
			ui.Warning(fmt.Sprintf("source staging: copy %q failed: %s — aborting staging", srcPath, err.Error()))
			stagingFinalErr = err
			terminalState = stagingFailed
			return
		}
	}

	newManifestPath := filepath.Join(newSrcPath, ".decepticon_staged")
	if err := os.WriteFile(newManifestPath, []byte(runID+"\n"), 0o644); err != nil {
		ui.Warning("source staging: could not write manifest — aborting: " + err.Error())
		stagingFinalErr = err
		terminalState = stagingFailed
		return
	}

	// Serialize promote/restore with a per-engagement file lock.
	lockPath := filepath.Join(stagingBase, ".staging.lock")
	lockFile, lockErr := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o644)
	if lockErr != nil {
		ui.Warning("source staging: could not open lock file: " + lockErr.Error())
		stagingFinalErr = lockErr
		terminalState = stagingFailed
		return
	}
	defer lockFile.Close()
	if err := syscall.Flock(int(lockFile.Fd()), syscall.LOCK_EX); err != nil {
		ui.Warning("source staging: could not acquire staging lock: " + err.Error())
		stagingFinalErr = err
		terminalState = stagingFailed
		return
	}
	defer func() { _ = syscall.Flock(int(lockFile.Fd()), syscall.LOCK_UN) }()

	manifestPath := filepath.Join(dstPath, ".decepticon_staged")
	hasPrev := false
	if _, statErr := statFn(dstPath); statErr == nil {
		if _, mErr := statFn(manifestPath); mErr != nil {
			ui.Warning(
				"source staging: /workspace/src exists without a launcher manifest — " +
					"skipping to protect manually created content. " +
					"Remove workspace/src to enable automatic staging.",
			)
			terminalState = stagingSkipped
			return
		}
		if err := os.Rename(dstPath, prevPath); err != nil {
			ui.Warning(fmt.Sprintf(
				"source staging: could not move previous /workspace/src aside: %s — "+
					"skipping to protect existing staged source",
				err.Error(),
			))
			stagingFinalErr = err
			terminalState = stagingFailed
			return
		}
		hasPrev = true
	}

	if err := os.Rename(newSrcPath, dstPath); err != nil {
		ui.Warning(fmt.Sprintf("source staging: promote failed: %s", err.Error()))
		if hasPrev {
			if restoreErr := os.Rename(prevPath, dstPath); restoreErr != nil {
				ui.Warning(fmt.Sprintf(
					"source staging: could not restore previous /workspace/src: %s — "+
						"previous tree is at %s; re-stage from %v to recover",
					restoreErr.Error(), prevPath, sourcePaths,
				))
			} else {
				_ = os.RemoveAll(prevPath)
			}
		}
		stagingFinalErr = err
		terminalState = stagingFailed
		return
	}

	if hasPrev {
		ui.DimText(fmt.Sprintf(
			"source staging: previous /workspace/src backed up at %s", prevPath,
		))
	}
	ui.DimText("Source staged at /workspace/src — analyst will find it there.")
	stagedSources = sourcePaths
	terminalState = stagingStaged
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
// exist. It defends against symlink and directory-swap attacks:
//   - Explicit symlinks in directory listings are skipped
//   - Every visited path is re-resolved with EvalSymlinks and verified to
//     remain within the canonical source root before it is processed; this
//     catches the race where a real directory is replaced with a symlink after
//     WalkDir's type check but before descent
//   - copyFilePath additionally guards each file against file-to-symlink swaps
//
// The budget parameter enforces cumulative size and depth limits; pass a
// non-nil *stagingBudget from stageSourceTargets. Walk errors are returned so
// the caller never promotes a partial copy.
func copyDirTree(src, dst string, budget *stagingBudget) error {
	realSrc, err := filepath.EvalSymlinks(src)
	if err != nil {
		return fmt.Errorf("cannot resolve source root %q: %w", src, err)
	}
	return filepath.WalkDir(src, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return fmt.Errorf("walk error at %q: %w", path, err)
		}
		// Skip explicit symlinks observed by WalkDir.
		if d.Type()&fs.ModeSymlink != 0 {
			ui.Warning(fmt.Sprintf("source staging: skipping symlink %q", path))
			return nil
		}
		// Re-resolve path after the DirEntry check to catch a directory-swap
		// race where a real dir was replaced with a symlink before descent.
		realPath, evalErr := filepath.EvalSymlinks(path)
		if evalErr != nil {
			return fmt.Errorf("cannot resolve %q — aborting staging: %w", path, evalErr)
		}
		if realPath != realSrc && !strings.HasPrefix(realPath, realSrc+string(filepath.Separator)) {
			return fmt.Errorf(
				"path %q resolved outside source root (real: %q, root: %q) — aborting staging",
				path, realPath, realSrc,
			)
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		// Depth check: number of separators in rel equals the tree depth.
		if rel != "." && budget != nil {
			depth := strings.Count(rel, string(filepath.Separator))
			if d.IsDir() {
				depth++ // directories count at their own level
			}
			if depth > budget.maxDepth {
				return fmt.Errorf(
					"path %q exceeds max staging depth %d — "+
						"raise DECEPTICON_MAX_STAGED_DEPTH to include deep trees",
					path, budget.maxDepth,
				)
			}
		}
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		// Size budget check before copy.
		if budget != nil {
			info, infoErr := d.Info()
			if infoErr != nil {
				return fmt.Errorf("cannot stat %q: %w", path, infoErr)
			}
			budget.bytesLeft -= info.Size()
			if budget.bytesLeft < 0 {
				return fmt.Errorf(
					"source tree exceeds staging size limit — "+
						"raise DECEPTICON_MAX_STAGED_BYTES to stage larger trees",
				)
			}
		}
		return copyFilePath(path, target)
	})
}

// copyFilePath copies a single regular file from src to dst, creating parent
// directories as needed. It guards against TOCTOU symlink attacks:
//   - os.Lstat rejects symlinks before the open call
//   - os.SameFile comparison after open detects if the path was swapped
//     between the Lstat and the Open (e.g. replaced with a symlink target)
func copyFilePath(src, dst string) error {
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}

	lstInfo, err := os.Lstat(src)
	if err != nil {
		return err
	}
	if lstInfo.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("source path %q is a symlink — refusing to copy", src)
	}
	if !lstInfo.Mode().IsRegular() {
		return fmt.Errorf("source path %q is not a regular file (type: %s) — skipping", src, lstInfo.Mode().Type().String())
	}

	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	// Guard against race between Lstat and Open where the path was swapped.
	openInfo, err := in.Stat()
	if err != nil {
		return err
	}
	if !os.SameFile(lstInfo, openInfo) {
		return fmt.Errorf("source path %q changed between stat and open — aborting copy", src)
	}

	// 0o600: not world-readable on the host. The sandbox bind-mount still
	// grants write access to processes running as root inside the container.
	// True read-only staging is future work.
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
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
