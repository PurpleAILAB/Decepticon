//go:build windows

package opscontrol

import (
	"os"
	"os/exec"
	"syscall"
)

// Windows has no systemd/launchd, so opscontrol always takes the
// launcher-spawn fallback path here. Process control is best-effort:
// the daemon is a degraded mode on Windows (no managed service), and
// these helpers exist so the package compiles and the fallback works
// well enough to spawn and tear down the daemon.

// terminateDaemon stops the daemon process. Windows has no SIGTERM, so
// this is a hard terminate.
func terminateDaemon(pid int) error {
	p, err := os.FindProcess(pid)
	if err != nil {
		return err
	}
	return p.Kill()
}

// processAlive reports whether pid names a live process. On Windows
// os.FindProcess opens a handle via OpenProcess and fails when the PID
// is not running, which is a good-enough liveness probe for the
// fallback supervisor.
func processAlive(pid int) bool {
	p, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	_ = p.Release()
	return true
}

// setDetached starts the daemon in its own process group so a Ctrl-C in
// the launcher console does not propagate to it.
func setDetached(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP}
}
