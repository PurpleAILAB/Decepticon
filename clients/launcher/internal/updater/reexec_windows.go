//go:build windows

package updater

import (
	"fmt"
	"os"
	"os/exec"
)

// reexecSelf re-runs the launcher binary as a child process and exits
// with its status code. Windows has no ``execve`` equivalent that
// replaces the running process, so the parent stays alive only long
// enough to wait for the child and propagate the exit code.
//
// stdin / stdout / stderr are inherited from the parent so the user's
// terminal session is uninterrupted. If the child cannot be spawned,
// the caller surfaces the error and falls back to a manual-restart
// message.
func reexecSelf() error {
	exe, err := os.Executable()
	if err != nil {
		return fmt.Errorf("get executable path: %w", err)
	}
	cmd := exec.Command(exe, os.Args[1:]...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = os.Environ()
	if err := cmd.Run(); err != nil {
		// ``cmd.Run`` returns the child's non-zero exit code wrapped in
		// *exec.ExitError — propagate that as our own exit so the user
		// sees the same status the new launcher returned.
		if exitErr, ok := err.(*exec.ExitError); ok {
			os.Exit(exitErr.ExitCode())
		}
		return fmt.Errorf("spawn %s: %w", exe, err)
	}
	os.Exit(0)
	return nil // unreachable
}
