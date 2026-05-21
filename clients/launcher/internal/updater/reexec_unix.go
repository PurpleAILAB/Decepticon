//go:build !windows

package updater

import (
	"fmt"
	"os"
	"syscall"
)

// reexecSelf replaces the current process with a fresh exec of the
// launcher binary, preserving argv and the environment. Used after a
// successful in-place self-update so the rest of the user's command
// runs against the just-installed binary instead of the in-memory copy
// of the previous version.
//
// On POSIX this is a true exec — control never returns on success,
// callers should treat the function as no-return. A non-nil error means
// the exec syscall itself failed (rare: missing executable, EACCES on
// the new binary, kernel ENOMEM); the caller should surface a "rerun
// manually" message and exit.
func reexecSelf() error {
	exe, err := os.Executable()
	if err != nil {
		return fmt.Errorf("get executable path: %w", err)
	}
	// ``syscall.Exec`` discards file descriptors with FD_CLOEXEC and
	// inherits the rest. stdin/stdout/stderr stay connected to the
	// parent terminal, which is exactly what the operator expects.
	if err := syscall.Exec(exe, os.Args, os.Environ()); err != nil {
		return fmt.Errorf("exec %s: %w", exe, err)
	}
	return nil // unreachable on success
}
