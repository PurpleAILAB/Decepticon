// Package starprompt presents a one-time GitHub star ask at the natural
// post-onboarding moment and again at the first interactive launch
// (before the engagement picker). Idempotent — a sentinel file at
// ${DECEPTICON_HOME}/.starred suppresses the prompt permanently after
// the first outcome (Yes / Skip / already-starred).
//
// Behaviour:
//   - Non-interactive stdin (CI, pipes) is a silent no-op. No ack is
//     written; the next interactive launch reconsiders.
//   - When `gh` is present and authenticated to github.com, the prompt
//     status-checks the repo and either stars in-place (PUT to
//     /user/starred/<repo>) or silently writes the ack when the user
//     has already starred.
//   - When `gh` is absent, unauthenticated, or any call errors/times
//     out, the prompt opens a browser (macOS `open`; WSL `wslview`
//     then `cmd.exe /c start`) and writes the ack regardless of the
//     browser's success.
//   - Every `gh` subprocess carries a 3-second deadline. The launcher
//     start flow can never be blocked by a hung `gh` process.
package starprompt

import (
	"os"
	"path/filepath"

	"charm.land/huh/v2"
	"golang.org/x/term"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

const (
	// AckFileName is the zero-byte sentinel inside DECEPTICON_HOME.
	// Presence alone is the signal — contents are intentionally empty
	// so an operator can suppress the prompt forever with
	// `touch ~/.decepticon/.starred` and re-enable it with `rm` of the
	// same path.
	AckFileName = ".starred"

	// RepoSlug is the canonical "owner/repo" used for every gh API
	// call and the browser URL. Hardcoded — no scenario justifies
	// targeting a different repository.
	RepoSlug = "PurpleAILAB/Decepticon"
	RepoURL  = "https://github.com/" + RepoSlug
)

// Function-variable indirections so tests can swap each external
// dependency without invoking real subprocesses, Huh prompts, or TTY
// checks. Matches the pattern PR #193 introduced for `executableFn`
// and `cmd/start.go` uses for `isWSLFn` / `wslHostIPFn`.
var (
	ghReadyFn         = ghReady
	checkStarStatusFn = checkStarStatus
	starViaGhFn       = starViaGh
	openBrowserFn     = openBrowserToRepo
	isInteractiveFn   = isInteractiveStdin
	confirmFn         = runConfirm
)

// PromptIfNotStarred is the only public entry. Safe to call from
// multiple sites (onboard end + start flow) because the ack-file
// check makes any subsequent call a no-op for users who have already
// gone through the prompt once.
func PromptIfNotStarred() {
	ackPath := filepath.Join(config.DecepticonHome(), AckFileName)

	// Stage 0 — already acknowledged.
	if _, err := os.Stat(ackPath); err == nil {
		return
	}

	// Stage 1 — silent skip on non-interactive stdin. No ack so the
	// next interactive launch reconsiders.
	if !isInteractiveFn() {
		return
	}

	// Stage 2 — gh graceful detection.
	if ghReadyFn() {
		switch checkStarStatusFn() {
		case statusStarred:
			// Already starred — write ack silently and return.
			touchAck(ackPath)
			return
		case statusNotStarred:
			promptViaGh(ackPath)
			return
		case statusUnknown:
			// gh call failed or timed out — fall through to browser.
		}
	}

	// Stage 3 — browser path (gh missing / unauthenticated / errored).
	promptViaBrowser(ackPath)
}

func promptViaGh(ackPath string) {
	confirmed := confirmFn(
		"★ Star Decepticon on GitHub?",
		"Detected gh CLI — we can star the repo in-place.\n"+RepoURL,
		"Yes, star now",
		"Skip",
	)
	if !confirmed {
		// Skip = permanent ack. The user opted out; do not nag.
		touchAck(ackPath)
		return
	}
	if err := starViaGhFn(); err != nil {
		// PUT failed — fall back to browser. The user already said Yes,
		// so preserve their intent rather than dropping it on the floor.
		ui.Warning("gh API call failed — opening browser instead.")
		if openErr := openBrowserFn(); openErr != nil {
			ui.Info("Please open: " + RepoURL)
		}
	} else {
		ui.Success("★ Starred. Thank you!")
	}
	touchAck(ackPath)
}

func promptViaBrowser(ackPath string) {
	confirmed := confirmFn(
		"★ Star Decepticon on GitHub?",
		"Opens "+RepoURL+" in your browser.",
		"Yes, open",
		"Skip",
	)
	if confirmed {
		if err := openBrowserFn(); err != nil {
			// Browser unavailable (headless SSH, missing wslu/interop) —
			// fall through to a textual hint.
			ui.Info("Please open: " + RepoURL)
		}
	}
	// Both Yes and Skip ack — Skip's intent is "don't ask again".
	touchAck(ackPath)
}

// touchAck writes the zero-byte sentinel. Best-effort: a write failure
// surfaces as a warning but does not abort the launch flow. The next
// interactive launch will retry because the ack file is missing.
func touchAck(path string) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		ui.Warning("Could not create " + filepath.Dir(path) + ": " + err.Error())
		return
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		ui.Warning("Could not write star-prompt ack: " + err.Error())
		return
	}
	_ = f.Close()
}

// runConfirm is the production Huh v2 Confirm renderer. A failure from
// Run() (TTY closed mid-render, terminal resize race, etc.) is treated
// as Skip — a user can never be accidentally signed up for an action.
func runConfirm(title, description, affirmative, negative string) bool {
	var v bool
	err := huh.NewConfirm().
		Title(title).
		Description(description).
		Affirmative(affirmative).
		Negative(negative).
		Value(&v).
		Run()
	if err != nil {
		return false
	}
	return v
}

func isInteractiveStdin() bool {
	return term.IsTerminal(int(os.Stdin.Fd()))
}
