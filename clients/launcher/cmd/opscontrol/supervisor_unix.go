//go:build !windows

package opscontrol

import (
	"os/exec"
	"syscall"
)

// terminateDaemon sends SIGTERM to the daemon process group.
func terminateDaemon(pid int) error {
	return syscall.Kill(pid, syscall.SIGTERM)
}

// processAlive reports whether pid names a live process. Signal 0 does
// not deliver a signal; it only runs the kernel's permission/existence
// check, which is the canonical liveness probe on Unix.
func processAlive(pid int) bool {
	return syscall.Kill(pid, syscall.Signal(0)) == nil
}

// setDetached puts the spawned daemon in its own session so it survives
// the launcher exiting (no controlling terminal, not in the launcher's
// process group).
func setDetached(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
}
