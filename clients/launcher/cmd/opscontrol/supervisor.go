package opscontrol

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"

	internal "github.com/PurpleAILAB/Decepticon/clients/launcher/internal/opscontrol"
)

// EnsureRunning is the launcher-side entry point: `decepticon start`
// calls it before `compose up`. The function is idempotent — if a
// healthy daemon is already running, it returns without starting a
// new one.
//
// It returns the host socket path so the caller can export it to
// docker compose (used by docker-compose.opscontrol.yml).
func EnsureRunning() (socketPath string, err error) {
	if err := internal.EnsureRunDir(); err != nil {
		return "", err
	}
	socketPath = internal.HostSocketPath()

	if pid, alive := readPID(); alive {
		// Daemon already running. Make sure the socket file is too;
		// if not, the daemon is unhealthy → kill and respawn.
		if info, err := os.Stat(socketPath); err == nil && info.Mode()&os.ModeSocket != 0 {
			return socketPath, nil
		}
		_ = syscall.Kill(pid, syscall.SIGTERM)
		_ = os.Remove(internal.PIDFilePath())
	}

	exe, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("opscontrol: locate self: %w", err)
	}
	// Spawn the daemon as a detached child of init. `setsid` puts it
	// in a new session so it survives the launcher exit.
	cmd := exec.Command(exe, "opscontrol", "daemon") //nolint:gosec // own binary
	cmd.Stdin = nil
	logf, lerr := os.OpenFile(daemonLogPath(), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if lerr == nil {
		cmd.Stdout = logf
		cmd.Stderr = logf
	}
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	cmd.Env = append(os.Environ(), "DECEPTICON_OPSCONTROL_CHILD=1")
	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("opscontrol: spawn daemon: %w", err)
	}
	// Detach: don't Wait so it keeps running. Release the process
	// reference so the launcher can exit cleanly.
	_ = cmd.Process.Release()

	// Wait for the socket to appear so `compose up` doesn't race
	// against an unbound mount target. 5s cap is generous; the
	// daemon binds in <100ms in practice.
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if info, err := os.Stat(socketPath); err == nil && info.Mode()&os.ModeSocket != 0 {
			return socketPath, nil
		}
		time.Sleep(50 * time.Millisecond)
	}
	return "", errors.New("opscontrol: daemon failed to bind socket within 5s; check " + daemonLogPath())
}

// Stop signals the daemon and waits up to 5s for it to exit. Called
// by `decepticon stop` after `compose down`.
func Stop() error {
	pid, alive := readPID()
	if !alive {
		return nil
	}
	if err := syscall.Kill(pid, syscall.SIGTERM); err != nil {
		return fmt.Errorf("opscontrol: signal daemon: %w", err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if _, alive := readPID(); !alive {
			_ = os.Remove(internal.HostSocketPath())
			return nil
		}
		time.Sleep(50 * time.Millisecond)
	}
	return errors.New("opscontrol: daemon did not exit within 5s")
}

// readPID returns the recorded daemon PID and whether the process is
// currently alive. A stale PID file (process gone) returns
// (pid, false), and callers usually treat that as "no daemon".
func readPID() (int, bool) {
	raw, err := os.ReadFile(internal.PIDFilePath())
	if err != nil {
		return 0, false
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(raw)))
	if err != nil || pid <= 0 {
		return 0, false
	}
	// Signal 0 probes liveness without delivering anything.
	if err := syscall.Kill(pid, syscall.Signal(0)); err != nil {
		return pid, false
	}
	return pid, true
}

func daemonLogPath() string {
	return internal.PIDFilePath() + ".log"
}
