package opscontrol

import (
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	internal "github.com/PurpleAILAB/Decepticon/clients/launcher/internal/opscontrol"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var installCmd = &cobra.Command{
	Use:   "install",
	Short: "Install opscontrol as a managed background service",
	Long: `Installs the opscontrol daemon as a systemd user unit (Linux,
including WSL2 with systemd=true) or a launchd LaunchAgent (macOS).

After install the daemon survives reboots, restarts automatically on
crash, and runs independently of the launcher — ` + "`decepticon start`" + ` /
` + "`decepticon stop`" + ` only manage the compose stack, not the daemon.

When the host does not have a recognized init system (Windows, WSL2
without systemd, Linux without per-user systemd), this command exits
with an explanatory note and the launcher keeps using the legacy
"spawn-as-child" mode automatically.`,
	RunE: runInstall,
}

func runInstall(_ *cobra.Command, _ []string) error {
	return EnsureInstalled()
}

// EnsureInstalled is the shared entry point used by `decepticon
// opscontrol install` and by the onboard wizard's post-config hook.
// Idempotent: re-running rewrites the unit (so a launcher upgrade
// updates the ExecStart path), then re-enables and restarts.
//
// On hosts without a recognized service manager this returns nil
// after logging a note — the launcher's spawn fallback continues to
// work, so onboard should not bail.
func EnsureInstalled() error {
	mgr := internal.DetectServiceManager()
	if !mgr.Available() {
		ui.Warning("No supported service manager on this host (looked for systemd-user, launchd).")
		ui.Info("opscontrol will use the launcher-spawn path automatically. No install action required.")
		return nil
	}

	exe, err := os.Executable()
	if err != nil {
		return fmt.Errorf("opscontrol: resolve binary path: %w", err)
	}

	// systemd's ReadWritePaths= refuses to set up the unit's mount
	// namespace if the path does not exist yet. Pre-create the home
	// directory and its run/ subdirectory so the very first start
	// after install succeeds. (Onboard normally creates these too;
	// this is the standalone `decepticon opscontrol install` path.)
	homePath := config.DecepticonHome()
	if err := os.MkdirAll(homePath, 0o700); err != nil {
		return fmt.Errorf("opscontrol: pre-create home: %w", err)
	}
	if err := internal.EnsureRunDir(); err != nil {
		return fmt.Errorf("opscontrol: pre-create run dir: %w", err)
	}

	spec := internal.InstallSpec{
		BinaryPath: exe,
		HomePath:   homePath,
		StackName:  internal.StackName(),
	}

	ui.Info(fmt.Sprintf("Installing opscontrol via %s (unit=%s)...", mgr.Name(), internal.ServiceUnitName()))
	if err := mgr.Install(spec); err != nil {
		return err
	}

	// systemd's `enable --now` returns as soon as the unit transitions
	// out of `inactive` — the daemon may still be `activating` when
	// the call returns. Poll until either `active` or the deadline
	// expires; failing fast on the first inactive read produced a
	// confusing "installed but not active" message in PR review.
	if err := waitForActive(mgr, 10*time.Second); err != nil {
		return err
	}

	ui.Success(fmt.Sprintf("opscontrol service is active. Socket: %s", internal.HostSocketPath()))
	return nil
}

// waitForActive polls until BOTH (a) mgr.Active() returns true AND
// (b) the host socket file exists as a real Unix socket. Checking
// only Active() is fragile: a unit that crash-loops via
// Restart=on-failure can flicker through `active`/`activating` states
// before the daemon has bound the socket — a stale "active" snapshot
// then lets install report success against a daemon that actually
// never started. Socket existence is the load-bearing signal because
// the agent contract IS the socket.
func waitForActive(mgr internal.ServiceManager, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	socketPath := internal.HostSocketPath()
	for time.Now().Before(deadline) {
		active, err := mgr.Active()
		if err != nil {
			return fmt.Errorf("opscontrol: probe active state: %w", err)
		}
		if active {
			if info, sErr := os.Stat(socketPath); sErr == nil && info.Mode()&os.ModeSocket != 0 {
				return nil
			}
		}
		time.Sleep(200 * time.Millisecond)
	}
	return errors.New("opscontrol: service did not reach active+socket-ready within " + timeout.String() +
		"; check `journalctl --user -u " + internal.ServiceUnitName() + "` or `launchctl print` output")
}

func init() {
	Cmd.AddCommand(installCmd)
}
