package opscontrol

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// SystemdManager owns a systemd user unit at
// ~/.config/systemd/user/decepticon-opscontrol[-${STACK}].service.
//
// User-level (not system-level) is intentional: the daemon runs as
// the operator's UID, talks to the docker socket as the same user
// (which is the only context that has docker group membership in
// most OSS installs), and writes only to $DECEPTICON_HOME — there is
// nothing root-only about the lifecycle.
type SystemdManager struct {
	UnitName string // e.g. "decepticon-opscontrol" or "decepticon-opscontrol-stack2"
}

func newSystemdManager() *SystemdManager {
	return &SystemdManager{UnitName: ServiceUnitName()}
}

// systemctlBinary lets tests inject a stub. Defaults to PATH lookup
// of `systemctl`.
var systemctlBinary = "systemctl"

// Available probes the user systemd bus. Three conditions must all
// hold:
//
//  1. The `systemctl` binary is on PATH.
//  2. /run/systemd/system exists (systemd is PID 1, or WSL2 has
//     systemd=true booted at session start).
//  3. `systemctl --user --version` exits 0 (the user manager is
//     reachable from this process — XDG_RUNTIME_DIR set, dbus up).
//
// Failure of any one degrades to noopManager via DetectServiceManager.
func (s *SystemdManager) Available() bool {
	if _, err := exec.LookPath(systemctlBinary); err != nil {
		return false
	}
	if _, err := os.Stat("/run/systemd/system"); err != nil {
		return false
	}
	if err := exec.Command(systemctlBinary, "--user", "--version").Run(); err != nil {
		return false
	}
	return true
}

func (s *SystemdManager) Name() string { return "systemd-user" }

func (s *SystemdManager) unitPath() (string, error) {
	dir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("opscontrol: resolve user home: %w", err)
	}
	return filepath.Join(dir, ".config", "systemd", "user", s.UnitName+".service"), nil
}

func (s *SystemdManager) Installed() (bool, error) {
	p, err := s.unitPath()
	if err != nil {
		return false, err
	}
	_, err = os.Stat(p)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	return err == nil, err
}

// Active calls `systemctl --user is-active <unit>`. Exit code 0 = active,
// non-zero = inactive (or not loaded). The string output is parsed for
// the canonical "active" answer so we don't silently treat "activating"
// as ready.
func (s *SystemdManager) Active() (bool, error) {
	out, err := exec.Command(systemctlBinary, "--user", "is-active", s.UnitName+".service").Output()
	state := strings.TrimSpace(string(out))
	if err != nil {
		// Treat "inactive"/"failed" as not-active without surfacing
		// the exit code as an error — the caller usually wants the
		// bool.
		if state == "" {
			return false, nil
		}
		return false, nil
	}
	return state == "active", nil
}

// Install writes (or re-writes) the unit file and enables + starts
// the service. Idempotent.
func (s *SystemdManager) Install(spec InstallSpec) error {
	if spec.BinaryPath == "" || spec.HomePath == "" {
		return errors.New("opscontrol: InstallSpec requires BinaryPath and HomePath")
	}
	unitDir, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("opscontrol: resolve user home: %w", err)
	}
	unitDir = filepath.Join(unitDir, ".config", "systemd", "user")
	if err := os.MkdirAll(unitDir, 0o755); err != nil {
		return fmt.Errorf("opscontrol: create systemd user dir: %w", err)
	}

	// Drop-in `*.conf` files override the unit we're about to write,
	// and they survive `Uninstall()` because that only removes the
	// .service file. v1.1.10 dogfood hit exactly this trap: a stale
	// `override.conf` pinned ExecStart= to /tmp/decepticon-stop-v3
	// (deleted between test runs), so `enable --now` succeeded but the
	// daemon failed with no error surfaced to the operator — they saw
	// `EnsureRunning` 5s socket timeout with no obvious cause.
	//
	// We only remove drop-ins whose ExecStart references a binary that
	// no longer exists on disk. Legitimate operator overrides (extra
	// env vars, restart policy tweaks) keep working.
	dropInRemoved := s.removeStaleDropIns(filepath.Join(unitDir, s.UnitName+".service.d"))

	unit := s.renderUnit(spec)
	unitFile := filepath.Join(unitDir, s.UnitName+".service")
	if err := os.WriteFile(unitFile, []byte(unit), 0o644); err != nil {
		return fmt.Errorf("opscontrol: write unit: %w", err)
	}

	if out, err := exec.Command(systemctlBinary, "--user", "daemon-reload").CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: daemon-reload: %w: %s", err, strings.TrimSpace(string(out)))
	}
	if dropInRemoved {
		// daemon-reload is required after drop-in removal too; the call
		// above covers both rewrites of the .service file and dropped
		// overrides in one pass.
		_ = exec.Command(systemctlBinary, "--user", "reset-failed", s.UnitName+".service").Run()
	}
	if out, err := exec.Command(systemctlBinary, "--user", "enable", "--now", s.UnitName+".service").CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: enable --now: %w: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// removeStaleDropIns deletes drop-in override files in `dir` whose
// ExecStart= points to a binary that no longer exists on disk. Returns
// true if any file was removed (the caller uses this to decide whether
// to also reset the unit's failed state).
//
// Scope is deliberately narrow: we only touch *.conf files we can
// prove are dead. Operator-authored overrides for live binaries
// (e.g. an extra Environment= line) survive untouched.
func (s *SystemdManager) removeStaleDropIns(dir string) bool {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return false
	}
	removed := false
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".conf") {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		body, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		for _, raw := range strings.Split(string(body), "\n") {
			line := strings.TrimSpace(raw)
			if !strings.HasPrefix(line, "ExecStart=") {
				continue
			}
			// Strip the `ExecStart=` prefix and any leading modifier
			// characters systemd accepts (`-`, `@`, `:`, `+`, `!`, `!!`).
			value := strings.TrimLeft(strings.TrimPrefix(line, "ExecStart="), "-@:+!")
			fields := strings.Fields(value)
			if len(fields) == 0 {
				continue
			}
			binaryPath := fields[0]
			if _, err := os.Stat(binaryPath); errors.Is(err, os.ErrNotExist) {
				fmt.Fprintf(os.Stderr,
					"opscontrol: removing stale drop-in %s — ExecStart=%s no longer exists\n",
					path, binaryPath)
				if err := os.Remove(path); err == nil {
					removed = true
				}
				break
			}
		}
	}
	// If the drop-in dir is now empty, remove it so a future
	// `systemctl edit` starts from a clean slate.
	if remaining, err := os.ReadDir(dir); err == nil && len(remaining) == 0 {
		_ = os.Remove(dir)
	}
	return removed
}

func (s *SystemdManager) Uninstall() error {
	// best-effort stop+disable so re-running uninstall after a manual
	// `systemctl stop` doesn't error.
	_ = exec.Command(systemctlBinary, "--user", "disable", "--now", s.UnitName+".service").Run()

	p, err := s.unitPath()
	if err != nil {
		return err
	}
	if err := os.Remove(p); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("opscontrol: remove unit file: %w", err)
	}
	// daemon-reload so systemd forgets the unit before another
	// install reuses the path.
	_ = exec.Command(systemctlBinary, "--user", "daemon-reload").Run()
	return nil
}

func (s *SystemdManager) Start() error {
	installed, err := s.Installed()
	if err != nil {
		return err
	}
	if !installed {
		return ErrNotInstalled
	}
	if out, err := exec.Command(systemctlBinary, "--user", "start", s.UnitName+".service").CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: systemctl start: %w: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

func (s *SystemdManager) Stop() error {
	// stop is fine to call even on a not-installed unit; systemctl
	// returns 0 with a warning. We swallow the warning.
	_ = exec.Command(systemctlBinary, "--user", "stop", s.UnitName+".service").Run()
	return nil
}

// renderUnit produces the .service file body. The sandbox knobs are
// deliberately narrow:
//
//   - Restart=on-failure with a 5s backoff covers the crash-recovery
//     gap the launcher-spawned mode had (problem #2 in the Alt A
//     design review).
//   - NoNewPrivileges blocks privilege escalation via setuid binaries.
//   - ProtectSystem=full keeps /usr, /boot, /efi read-only without
//     touching /etc (docker-cli reads /etc/docker/, /etc/resolv.conf,
//     etc.). `strict` was tried and broke docker-cli reads in WSL2.
//   - ProtectHome=read-only + ReadWritePaths=$DECEPTICON_HOME narrows
//     the home write surface to just the data directory without
//     blocking docker-cli reads of ~/.docker/config.json etc.
//
// `PrivateTmp=true` was intentionally dropped: the daemon does not
// read or write /tmp during normal operation, so the hardening is
// nearly zero-value, while the mount-namespace setup breaks any
// install whose binary lives under /tmp (CI sandboxes, source
// builds). The audit trail is preserved in the original ADR-0006
// Alt A design notes.
//
// We do NOT use socket activation in v1.1.8 — the daemon always runs
// when enabled. Socket activation is a future-Sprint reduction.
func (s *SystemdManager) renderUnit(spec InstallSpec) string {
	stackEnv := ""
	if spec.StackName != "" {
		stackEnv = fmt.Sprintf("Environment=DECEPTICON_STACK_NAME=%s\n", spec.StackName)
	}
	// WorkingDirectory MUST be $DECEPTICON_HOME because compose's
	// config-hash mixes the project working dir into the per-container
	// label. Without this the daemon spawns containers with
	// `com.docker.compose.project.working_dir=/` and the launcher's
	// containers with `working_dir=<wherever the launcher was run>`,
	// producing different config-hashes for the *same* services and
	// forcing `compose up` to mark every existing container "Recreate"
	// on the next ops_start.
	//
	// EnvironmentFile pulls $DECEPTICON_HOME/.env so the daemon's
	// compose subprocess sees the same interpolation env (image tags,
	// ports, passwords, …) the launcher saw. The leading `-` keeps
	// install tolerant of `.env` not existing yet.
	return fmt.Sprintf(`[Unit]
Description=Decepticon opscontrol daemon (ADR-0006)
Documentation=https://github.com/PurpleAILAB/Decepticon/blob/main/docs/adr/0006-agent-driven-container-lifecycle.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%s opscontrol daemon
WorkingDirectory=%s
EnvironmentFile=-%s/.env
Environment=DECEPTICON_HOME=%s
%sRestart=on-failure
RestartSec=5s
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=%s
SyslogIdentifier=%s

[Install]
WantedBy=default.target
`, spec.BinaryPath, spec.HomePath, spec.HomePath, spec.HomePath, stackEnv, spec.HomePath, s.UnitName)
}
