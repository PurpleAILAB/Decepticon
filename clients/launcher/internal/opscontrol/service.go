package opscontrol

import (
	"errors"
	"runtime"
)

// ServiceManager abstracts the OS-native init system that owns the
// opscontrol daemon's lifecycle in Alt A (ADR-0006 supervision
// addendum). The launcher's `decepticon start` / `decepticon stop`
// flows defer to whichever ServiceManager is active on the host;
// when none is, they fall back to the pre-Alt-A pattern of spawning
// the daemon as a launcher child.
//
// Implementations:
//
//   - SystemdManager (Linux + user systemd, including WSL2 with
//     systemd=true in /etc/wsl.conf)
//   - LaunchdManager (macOS user LaunchAgent)
//   - noopManager    (every other host — Windows, WSL2 without
//                     systemd, Linux without per-user systemd)
//
// Every method is idempotent. Install on an already-installed unit
// re-writes the unit file (so binary-path / DECEPTICON_HOME drift
// gets corrected on the next install run), then re-enables and
// re-starts. Uninstall on a never-installed unit is a no-op.
type ServiceManager interface {
	// Name returns the implementation tag for diagnostics
	// ("systemd-user", "launchd", "none").
	Name() string

	// Available reports whether the manager can act on this host.
	// `noopManager` always returns false; the platform-specific ones
	// probe their init system before returning true.
	Available() bool

	// Installed reports whether the daemon's service unit currently
	// exists on disk (not whether it is *running*). Returns (false,
	// nil) for the noop manager.
	Installed() (bool, error)

	// Active reports whether the service is currently running per the
	// init system. For noop returns false.
	Active() (bool, error)

	// Install writes (or re-writes) the unit file, reloads the init
	// system, enables the unit (so it starts on boot/login), and
	// starts it. Idempotent.
	Install(spec InstallSpec) error

	// Uninstall stops the service, disables it, and removes the unit
	// file. Idempotent: a never-installed unit is a no-op.
	Uninstall() error

	// Start starts the service if installed but not active.
	// No-op when already active. Errors when not installed.
	Start() error

	// Stop stops the service if active. No-op when already inactive.
	Stop() error
}

// InstallSpec carries every value the manager needs to template the
// unit file. Built once by `decepticon opscontrol install` from the
// launcher's resolved config (binary path via os.Executable(), home
// path via config.DecepticonHome()).
type InstallSpec struct {
	// BinaryPath is the absolute path of the `decepticon` binary the
	// service will exec. Resolved via os.Executable() so the service
	// targets whichever copy the user just installed (homebrew, deb,
	// /usr/local/bin/decepticon, ~/.local/bin/decepticon).
	BinaryPath string

	// HomePath is the absolute $DECEPTICON_HOME directory. Templated
	// into Environment= / EnvironmentVariables= so the daemon resolves
	// the same socket path the launcher does.
	HomePath string

	// StackName is the DECEPTICON_STACK_NAME at install time (or
	// empty). Templated into the unit name + Environment so two
	// stacks coexist without colliding socket paths or unit names.
	StackName string
}

// DetectServiceManager returns the best ServiceManager for the host.
// Order:
//
//  1. SystemdManager when GOOS=linux AND systemd user bus is
//     reachable. WSL2 with systemd=true qualifies.
//  2. LaunchdManager when GOOS=darwin.
//  3. noopManager otherwise — caller falls back to launcher-spawned
//     mode.
func DetectServiceManager() ServiceManager {
	switch runtime.GOOS {
	case "linux":
		sm := newSystemdManager()
		if sm.Available() {
			return sm
		}
	case "darwin":
		lm := newLaunchdManager()
		if lm.Available() {
			return lm
		}
	}
	return noopManager{}
}

// ErrNotInstalled is returned by Start when the unit is not present.
var ErrNotInstalled = errors.New("opscontrol: service is not installed; run `decepticon opscontrol install` first")

// noopManager is the fallback for environments without a recognized
// init system. Every method is a benign no-op (or returns false) so
// the launcher path stays untouched.
type noopManager struct{}

func (noopManager) Name() string                  { return "none" }
func (noopManager) Available() bool               { return false }
func (noopManager) Installed() (bool, error)      { return false, nil }
func (noopManager) Active() (bool, error)         { return false, nil }
func (noopManager) Install(_ InstallSpec) error   { return errors.New("opscontrol: no service manager available on this host (falling back to launcher-spawned mode)") }
func (noopManager) Uninstall() error              { return nil }
func (noopManager) Start() error                  { return ErrNotInstalled }
func (noopManager) Stop() error                   { return nil }
