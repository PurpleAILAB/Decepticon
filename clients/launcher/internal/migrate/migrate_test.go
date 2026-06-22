package migrate

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
)

func newTestCtx(t *testing.T, env map[string]string, tty bool) *Ctx {
	t.Helper()
	home := t.TempDir()
	envPath := filepath.Join(home, ".env")
	// A minimal .env so file-writing steps have something to edit.
	if _, ok := env["DECEPTICON_TELEMETRY"]; ok {
		_ = os.WriteFile(envPath, []byte("DECEPTICON_TELEMETRY="+env["DECEPTICON_TELEMETRY"]+"\n"), 0o600)
	} else {
		_ = os.WriteFile(envPath, []byte("FOO=bar\n"), 0o600)
	}
	c := &Ctx{
		EnvPath: envPath,
		Env:     env,
		Home:    home,
		IsTTY:   tty,
		ackPath: filepath.Join(home, ackFileName),
	}
	c.loadAcks()
	return c
}

func TestRun_NonInteractiveStepAlwaysRuns(t *testing.T) {
	c := newTestCtx(t, map[string]string{}, false)
	ran := 0
	Run(c, []Step{{
		ID:          "noninteractive",
		Interactive: false,
		Apply:       func(_ *Ctx) (string, error) { ran++; return "", nil },
	}})
	if ran != 1 {
		t.Fatalf("non-interactive step ran %d times, want 1", ran)
	}
	// Non-interactive steps are never ack-recorded (they re-run each start).
	if c.Acked("noninteractive") {
		t.Error("non-interactive step should not be ack-recorded")
	}
}

func TestRun_InteractiveDeferredOnNonTTY(t *testing.T) {
	c := newTestCtx(t, map[string]string{}, false)
	ran := 0
	step := Step{
		ID:          "consent",
		Interactive: true,
		Apply:       func(_ *Ctx) (string, error) { ran++; return "", nil },
	}
	Run(c, []Step{step})
	if ran != 0 {
		t.Fatalf("interactive step ran on non-TTY (%d), want deferred", ran)
	}
	if c.Acked("consent") {
		t.Error("deferred step must not be acked")
	}
}

func TestRun_InteractiveRunsOnceThenAcked(t *testing.T) {
	c := newTestCtx(t, map[string]string{}, true)
	ran := 0
	step := Step{
		ID:          "consent",
		Interactive: true,
		Apply:       func(_ *Ctx) (string, error) { ran++; return "ok", nil },
	}
	Run(c, []Step{step})
	Run(c, []Step{step}) // second start: already acked
	if ran != 1 {
		t.Fatalf("interactive step ran %d times, want exactly 1", ran)
	}
	if !c.Acked("consent") {
		t.Error("interactive step should be acked after running")
	}
	// Ack persists across a fresh Ctx (simulating a new process).
	c2 := &Ctx{ackPath: c.ackPath}
	c2.loadAcks()
	if !c2.Acked("consent") {
		t.Error("ack did not persist to disk")
	}
}

func TestTelemetryReconsent_Yes(t *testing.T) {
	defer swapConfirm(true)()
	c := newTestCtx(t, map[string]string{"DECEPTICON_TELEMETRY": "off"}, true)
	if _, err := applyTelemetryReconsent(c); err != nil {
		t.Fatalf("applyTelemetryReconsent: %v", err)
	}
	assertEnvKey(t, c.EnvPath, "DECEPTICON_TELEMETRY", "research")
	if c.Env["DECEPTICON_TELEMETRY"] != "research" {
		t.Errorf("in-memory env not updated: %q", c.Env["DECEPTICON_TELEMETRY"])
	}
}

func TestTelemetryReconsent_No(t *testing.T) {
	defer swapConfirm(false)()
	c := newTestCtx(t, map[string]string{"DECEPTICON_TELEMETRY": "off"}, true)
	if _, err := applyTelemetryReconsent(c); err != nil {
		t.Fatalf("applyTelemetryReconsent: %v", err)
	}
	assertEnvKey(t, c.EnvPath, "DECEPTICON_TELEMETRY", "off")
}

func TestTelemetryReconsent_HardOptOutDoNotTrack(t *testing.T) {
	// DO_NOT_TRACK must skip the prompt entirely and leave the value alone.
	called := false
	restore := confirm
	confirm = func(_, _, _, _ string, _ bool) bool { called = true; return true }
	defer func() { confirm = restore }()

	c := newTestCtx(t, map[string]string{"DECEPTICON_TELEMETRY": "off", "DO_NOT_TRACK": "1"}, true)
	if _, err := applyTelemetryReconsent(c); err != nil {
		t.Fatalf("applyTelemetryReconsent: %v", err)
	}
	if called {
		t.Error("prompt shown despite DO_NOT_TRACK")
	}
	assertEnvKey(t, c.EnvPath, "DECEPTICON_TELEMETRY", "off")
}

func TestTelemetryReconsent_HardOptOutMarker(t *testing.T) {
	called := false
	restore := confirm
	confirm = func(_, _, _, _ string, _ bool) bool { called = true; return true }
	defer func() { confirm = restore }()

	c := newTestCtx(t, map[string]string{"DECEPTICON_TELEMETRY": "off"}, true)
	markerDir := filepath.Join(c.Home, "telemetry")
	if err := os.MkdirAll(markerDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(markerDir, "opt_out"), []byte("opted out\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := applyTelemetryReconsent(c); err != nil {
		t.Fatalf("applyTelemetryReconsent: %v", err)
	}
	if called {
		t.Error("prompt shown despite opt-out marker")
	}
	assertEnvKey(t, c.EnvPath, "DECEPTICON_TELEMETRY", "off")
}

func TestEnvBackfillStepReflectsIntoEnv(t *testing.T) {
	c := newTestCtx(t, map[string]string{"DECEPTICON_TELEMETRY": "off"}, false)
	if _, err := applyEnvBackfill(c); err != nil {
		t.Fatalf("applyEnvBackfill: %v", err)
	}
	// The endpoint (a template default missing from the seed) should now be
	// both on disk and reflected into the in-memory env map.
	if c.Env["DECEPTICON_TELEMETRY_ENDPOINT"] == "" {
		t.Error("backfilled key not reflected into in-memory env")
	}
}

// TestRunAll_ExistingUserUpgrade exercises the fully wired path an existing
// (pre-endpoint) user hits at `decepticon start`: env-backfill adds the
// telemetry endpoint their .env never had, and the one-time re-consent
// prompt flips them to research — then never fires again.
func TestRunAll_ExistingUserUpgrade(t *testing.T) {
	home := t.TempDir()
	t.Setenv("DECEPTICON_HOME", home)
	envPath := filepath.Join(home, ".env")
	// A pre-#706 .env: telemetry off, NO endpoint key at all.
	if err := os.WriteFile(envPath, []byte("DECEPTICON_TELEMETRY=off\nANTHROPIC_API_KEY=sk-real\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	defer swapConfirm(true)()
	restoreTTY := isInteractive
	isInteractive = func() bool { return true }
	defer func() { isInteractive = restoreTTY }()

	env, err := config.LoadEnv(envPath)
	if err != nil {
		t.Fatal(err)
	}
	RunAll(env)

	got, err := config.LoadEnv(envPath)
	if err != nil {
		t.Fatal(err)
	}
	if got["DECEPTICON_TELEMETRY_ENDPOINT"] == "" {
		t.Error("endpoint not backfilled for existing user")
	}
	if got["DECEPTICON_TELEMETRY"] != "research" {
		t.Errorf("DECEPTICON_TELEMETRY = %q, want research after consent", got["DECEPTICON_TELEMETRY"])
	}
	if got["ANTHROPIC_API_KEY"] != "sk-real" {
		t.Errorf("real key not preserved: %q", got["ANTHROPIC_API_KEY"])
	}

	// Second start: consent must NOT be asked again.
	asked := false
	confirm = func(_, _, _, _ string, _ bool) bool { asked = true; return true }
	env2, _ := config.LoadEnv(envPath)
	RunAll(env2)
	if asked {
		t.Error("re-consent prompt fired a second time (ack not honored)")
	}
}

// --- helpers ---

func swapConfirm(answer bool) func() {
	restore := confirm
	confirm = func(_, _, _, _ string, _ bool) bool { return answer }
	return func() { confirm = restore }
}

func assertEnvKey(t *testing.T, path, key, want string) {
	t.Helper()
	env, err := config.LoadEnv(path)
	if err != nil {
		t.Fatalf("LoadEnv: %v", err)
	}
	if env[key] != want {
		t.Errorf("%s = %q, want %q", key, env[key], want)
	}
}
