package starprompt

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

// withTempHome redirects config.DecepticonHome() output via env so each
// test owns its own ack-file directory.
func withTempHome(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("DECEPTICON_HOME", dir)
	return dir
}

// stubs collects the externally-injectable state for one test. Tests
// set the fields they care about; install() swaps the function
// variables and t.Cleanup restores originals.
type stubs struct {
	ghReady       bool
	starStatus    starStatus
	starErr       error
	openErr       error
	interactive   bool
	confirmReturn bool

	openCalled    bool
	starGhCalled  bool
	confirmCalled bool
	confirmTitle  string
}

func install(t *testing.T, s *stubs) {
	t.Helper()
	origGhReady := ghReadyFn
	origStatus := checkStarStatusFn
	origStar := starViaGhFn
	origOpen := openBrowserFn
	origInteractive := isInteractiveFn
	origConfirm := confirmFn

	ghReadyFn = func() bool { return s.ghReady }
	checkStarStatusFn = func() starStatus { return s.starStatus }
	starViaGhFn = func() error {
		s.starGhCalled = true
		return s.starErr
	}
	openBrowserFn = func() error {
		s.openCalled = true
		return s.openErr
	}
	isInteractiveFn = func() bool { return s.interactive }
	confirmFn = func(title, _, _, _ string) bool {
		s.confirmCalled = true
		s.confirmTitle = title
		return s.confirmReturn
	}

	t.Cleanup(func() {
		ghReadyFn = origGhReady
		checkStarStatusFn = origStatus
		starViaGhFn = origStar
		openBrowserFn = origOpen
		isInteractiveFn = origInteractive
		confirmFn = origConfirm
	})
}

func ackExists(t *testing.T, home string) bool {
	t.Helper()
	_, err := os.Stat(filepath.Join(home, AckFileName))
	return err == nil
}

// ── Stage 0: ack already present ────────────────────────────────────

func TestPromptIfNotStarred_AckExists_Returns(t *testing.T) {
	home := withTempHome(t)
	if err := os.WriteFile(filepath.Join(home, AckFileName), nil, 0o644); err != nil {
		t.Fatalf("seed ack: %v", err)
	}
	s := &stubs{interactive: true, ghReady: true}
	install(t, s)

	PromptIfNotStarred()

	if s.confirmCalled || s.openCalled || s.starGhCalled {
		t.Error("ack present must short-circuit before any side effect")
	}
}

// ── Stage 1: non-interactive ────────────────────────────────────────

func TestPromptIfNotStarred_NonInteractive_SilentNoOp(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{interactive: false, ghReady: true}
	install(t, s)

	PromptIfNotStarred()

	if s.confirmCalled || s.openCalled || s.starGhCalled {
		t.Error("non-interactive stdin must produce no side effects")
	}
	if ackExists(t, home) {
		t.Error("non-interactive must NOT write ack (next interactive retries)")
	}
}

// ── Stage 2a: gh present, already starred ───────────────────────────

func TestPromptIfNotStarred_GhAlreadyStarred_SilentAck(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{interactive: true, ghReady: true, starStatus: statusStarred}
	install(t, s)

	PromptIfNotStarred()

	if s.confirmCalled {
		t.Error("already-starred path must not show a prompt")
	}
	if !ackExists(t, home) {
		t.Error("already-starred must write ack")
	}
}

// ── Stage 2b: gh present, not starred, user picks Yes ───────────────

func TestPromptIfNotStarred_GhNotStarred_YesStarsInPlace(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       true,
		starStatus:    statusNotStarred,
		confirmReturn: true,
	}
	install(t, s)

	PromptIfNotStarred()

	if !s.starGhCalled {
		t.Error("Yes via gh path must call starViaGh")
	}
	if s.openCalled {
		t.Error("Yes via gh path must NOT open browser when gh succeeds")
	}
	if !ackExists(t, home) {
		t.Error("Yes outcome must write ack")
	}
}

// ── Stage 2c: gh present, not starred, user picks Skip ──────────────

func TestPromptIfNotStarred_GhNotStarred_SkipAcksOnly(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       true,
		starStatus:    statusNotStarred,
		confirmReturn: false,
	}
	install(t, s)

	PromptIfNotStarred()

	if s.starGhCalled || s.openCalled {
		t.Error("Skip must not invoke star/open")
	}
	if !ackExists(t, home) {
		t.Error("Skip must write ack (permanent)")
	}
}

// ── Stage 2d: gh PUT fails → browser fallback + ack ─────────────────

func TestPromptIfNotStarred_GhPutFails_FallsBackToBrowser(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       true,
		starStatus:    statusNotStarred,
		confirmReturn: true,
		starErr:       errors.New("gh PUT failed"),
	}
	install(t, s)

	PromptIfNotStarred()

	if !s.starGhCalled {
		t.Error("gh path must attempt PUT first")
	}
	if !s.openCalled {
		t.Error("gh PUT failure must fall back to browser open")
	}
	if !ackExists(t, home) {
		t.Error("ack must still be written after fallback")
	}
}

// ── Stage 2e: gh present, status unknown → browser ──────────────────

func TestPromptIfNotStarred_StatusUnknown_BrowserPath(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       true,
		starStatus:    statusUnknown,
		confirmReturn: true,
	}
	install(t, s)

	PromptIfNotStarred()

	if s.starGhCalled {
		t.Error("statusUnknown must NOT attempt gh PUT (no trustworthy signal)")
	}
	if !s.openCalled {
		t.Error("statusUnknown must fall through to browser")
	}
	if !ackExists(t, home) {
		t.Error("browser-path Yes must write ack")
	}
}

// ── Stage 3: gh absent, user picks Yes → browser ────────────────────

func TestPromptIfNotStarred_NoGh_YesOpensBrowser(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       false,
		confirmReturn: true,
	}
	install(t, s)

	PromptIfNotStarred()

	if !s.openCalled {
		t.Error("no gh + Yes must open browser")
	}
	if s.starGhCalled {
		t.Error("no gh path must never call starViaGh")
	}
	if !ackExists(t, home) {
		t.Error("Yes via browser must write ack")
	}
}

// ── Stage 3b: gh absent, user picks Skip ────────────────────────────

func TestPromptIfNotStarred_NoGh_SkipAcksOnly(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       false,
		confirmReturn: false,
	}
	install(t, s)

	PromptIfNotStarred()

	if s.openCalled || s.starGhCalled {
		t.Error("Skip must not invoke browser or star")
	}
	if !ackExists(t, home) {
		t.Error("Skip via browser path must write ack")
	}
}

// ── Stage 3c: browser open fails → URL hint, ack still written ──────

func TestPromptIfNotStarred_NoGh_BrowserOpenFails_StillAcks(t *testing.T) {
	home := withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       false,
		confirmReturn: true,
		openErr:       errors.New("xdg-open not found"),
	}
	install(t, s)

	PromptIfNotStarred()

	if !s.openCalled {
		t.Error("browser path Yes must attempt open even if it will fail")
	}
	if !ackExists(t, home) {
		t.Error("open failure must not block ack — user picked Yes intentionally")
	}
}

// ── Prompt routing — title matches the path ─────────────────────────

func TestPromptIfNotStarred_GhPath_TitleSet(t *testing.T) {
	withTempHome(t)
	s := &stubs{
		interactive:   true,
		ghReady:       true,
		starStatus:    statusNotStarred,
		confirmReturn: false,
	}
	install(t, s)

	PromptIfNotStarred()

	if s.confirmTitle != "★ Star Decepticon on GitHub?" {
		t.Errorf("title = %q, want gh-path star ask", s.confirmTitle)
	}
}

// ── starStatus enum sanity ──────────────────────────────────────────

func TestStarStatus_DistinctEnum(t *testing.T) {
	if statusUnknown == statusStarred ||
		statusUnknown == statusNotStarred ||
		statusStarred == statusNotStarred {
		t.Error("starStatus values must be distinct")
	}
}
