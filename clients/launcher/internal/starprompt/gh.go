package starprompt

import (
	"context"
	"errors"
	"io"
	"os/exec"
	"time"
)

// ghCallTimeout bounds every subprocess call against the gh CLI.
// The launcher's start flow must never block on a stalled gh process.
const ghCallTimeout = 3 * time.Second

type starStatus int

const (
	statusUnknown starStatus = iota
	statusStarred
	statusNotStarred
)

// ghReady reports whether the `gh` binary is on PATH AND the user is
// authenticated specifically to github.com. Authentication only to a
// non-github.com host (e.g. an Enterprise instance) is intentionally
// not enough — the star endpoint lives on github.com.
func ghReady() bool {
	if _, err := exec.LookPath("gh"); err != nil {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), ghCallTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "gh", "auth", "status",
		"--hostname", "github.com")
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard
	return cmd.Run() == nil
}

// checkStarStatus runs `gh api /user/starred/<slug>`. The endpoint
// returns 204 when the user has starred the repo and 404 otherwise;
// gh maps the 204 to a clean exit and the 404 to exit code 1. Any
// other failure (network, scope, timeout) returns statusUnknown so
// the caller falls back to the browser path.
func checkStarStatus() starStatus {
	ctx, cancel := context.WithTimeout(context.Background(), ghCallTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "gh", "api",
		"/user/starred/"+RepoSlug, "--silent")
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard
	err := cmd.Run()
	if err == nil {
		return statusStarred
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
		return statusNotStarred
	}
	return statusUnknown
}

// starViaGh issues PUT /user/starred/<slug> through the gh CLI. Any
// non-nil error means the caller should fall back to opening a
// browser — we never re-attempt the PUT to avoid double-starring or
// looping on a permanent error like a missing scope.
func starViaGh() error {
	ctx, cancel := context.WithTimeout(context.Background(), ghCallTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "gh", "api", "-X", "PUT",
		"/user/starred/"+RepoSlug, "--silent")
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard
	return cmd.Run()
}
