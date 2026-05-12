package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// withStagingStubs swaps the staging DI variables for one test, restoring them
// via t.Cleanup. Sets pollIntervalVar=0 (no sleep) and maxAttemptsVar to the
// provided value.
func withStagingStubs(t *testing.T, maxAttempts int) {
	t.Helper()
	prevRead := readFileFn
	prevStat := statFn
	prevNow := nowFn
	prevInterval := pollIntervalVar
	prevMax := maxAttemptsVar
	pollIntervalVar = 0
	maxAttemptsVar = maxAttempts
	t.Cleanup(func() {
		readFileFn = prevRead
		statFn = prevStat
		nowFn = prevNow
		pollIntervalVar = prevInterval
		maxAttemptsVar = prevMax
	})
}

// writePlanDocs writes conops.json and deconfliction.json into planDir with
// minimal valid JSON. Does NOT write roe.json or the marker — use writeRoE
// and writeBundleMarker separately.
func writePlanDocs(t *testing.T, planDir string) {
	t.Helper()
	_ = os.MkdirAll(planDir, 0o755)
	for _, doc := range []string{"conops.json", "deconfliction.json"} {
		if err := os.WriteFile(filepath.Join(planDir, doc), []byte(`{}`), 0o644); err != nil {
			t.Fatalf("writePlanDocs: write %s: %v", doc, err)
		}
	}
}

// writeBundleMarker sleeps 2ms (to ensure mtime is newer than recently written
// docs) then writes .bundle_complete into planDir.
func writeBundleMarker(t *testing.T, planDir string) {
	t.Helper()
	time.Sleep(2 * time.Millisecond)
	body, _ := json.Marshal(map[string]interface{}{"schema_version": 1})
	if err := os.WriteFile(filepath.Join(planDir, ".bundle_complete"), body, 0o644); err != nil {
		t.Fatalf("writeBundleMarker: %v", err)
	}
}

// writeRoE writes roe.json with the given scope entries (in_scope key).
func writeRoE(t *testing.T, planDir string, targets []map[string]string) {
	t.Helper()
	type entry struct {
		Target string `json:"target"`
		Type   string `json:"type"`
	}
	roe := struct {
		InScope []entry `json:"in_scope"`
	}{}
	for _, m := range targets {
		roe.InScope = append(roe.InScope, entry{Target: m["target"], Type: m["type"]})
	}
	data, _ := json.Marshal(roe)
	if err := os.WriteFile(filepath.Join(planDir, "roe.json"), data, 0o644); err != nil {
		t.Fatalf("writeRoE: %v", err)
	}
}

// setupPlanBundle writes all three plan docs + marker in the correct mtime
// order (docs first, marker last) for a given RoE target list.
func setupPlanBundle(t *testing.T, planDir string, roeTargets []map[string]string) {
	t.Helper()
	writePlanDocs(t, planDir)
	writeRoE(t, planDir, roeTargets)
	writeBundleMarker(t, planDir)
}

// readStatusFile reads and parses staging-status.json from the workspace.
func readStatusFile(t *testing.T, workspacePath string) map[string]interface{} {
	t.Helper()
	path := filepath.Join(workspacePath, ".decepticon", "staging-status.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("readStatusFile: %v", err)
	}
	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("readStatusFile: unmarshal: %v", err)
	}
	return m
}

// ── sanitizeDirName ───────────────────────────────────────────────────────────

func TestSanitizeDirName_ReplacesUnsafeChars(t *testing.T) {
	cases := []struct{ in, want string }{
		{"my/project", "my_project"},
		{"a\\b:c*d?e\"f<g>h|i", "a_b_c_d_e_f_g_h_i"},
		{"normal-name", "normal-name"},
		{"", ""},
	}
	for _, c := range cases {
		got := sanitizeDirName(c.in)
		if got != c.want {
			t.Errorf("sanitizeDirName(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// ── copyFilePath ──────────────────────────────────────────────────────────────

func TestCopyFilePath_CreatesFileWith0600(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.txt")
	dst := filepath.Join(dir, "dst.txt")
	if err := os.WriteFile(src, []byte("hello"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := copyFilePath(src, dst); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(dst)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Errorf("mode = %o, want 0600", info.Mode().Perm())
	}
}

func TestCopyFilePath_RejectsSymlinkSource(t *testing.T) {
	dir := t.TempDir()
	real := filepath.Join(dir, "real.txt")
	link := filepath.Join(dir, "link.txt")
	_ = os.WriteFile(real, []byte("x"), 0o644)
	if err := os.Symlink(real, link); err != nil {
		t.Skip("symlinks not supported:", err)
	}
	if err := copyFilePath(link, filepath.Join(dir, "dst.txt")); err == nil {
		t.Error("expected error for symlink source")
	}
}

func TestCopyFilePath_RejectsNonRegular(t *testing.T) {
	dir := t.TempDir()
	// a directory is not a regular file
	if err := copyFilePath(dir, filepath.Join(dir, "out.txt")); err == nil {
		t.Error("expected error for directory source")
	}
}

// ── copyDirTree ───────────────────────────────────────────────────────────────

func TestCopyDirTree_HappyPath(t *testing.T) {
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "a.txt"), []byte("aaa"), 0o644)
	_ = os.MkdirAll(filepath.Join(src, "sub"), 0o755)
	_ = os.WriteFile(filepath.Join(src, "sub", "b.txt"), []byte("bbb"), 0o644)

	dst := t.TempDir()
	budget := &stagingBudget{bytesLeft: 1 << 20, maxDepth: 32}
	if err := copyDirTree(src, dst, budget); err != nil {
		t.Fatal(err)
	}
	for _, rel := range []string{"a.txt", "sub/b.txt"} {
		if _, err := os.Stat(filepath.Join(dst, rel)); err != nil {
			t.Errorf("missing %s", rel)
		}
	}
}

func TestCopyDirTree_SkipsSymlinkEntries(t *testing.T) {
	src := t.TempDir()
	real := filepath.Join(src, "real.txt")
	_ = os.WriteFile(real, []byte("x"), 0o644)
	link := filepath.Join(src, "link.txt")
	if err := os.Symlink(real, link); err != nil {
		t.Skip("symlinks not supported:", err)
	}

	dst := t.TempDir()
	budget := &stagingBudget{bytesLeft: 1 << 20, maxDepth: 32}
	if err := copyDirTree(src, dst, budget); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dst, "link.txt")); err == nil {
		t.Error("symlink should not have been copied")
	}
	if _, err := os.Stat(filepath.Join(dst, "real.txt")); err != nil {
		t.Error("real file should have been copied")
	}
}

func TestCopyDirTree_AbortsOnDepthExceeded(t *testing.T) {
	src := t.TempDir()
	// Create a 3-level deep file: src/a/b/c/file.txt
	deep := filepath.Join(src, "a", "b", "c")
	_ = os.MkdirAll(deep, 0o755)
	_ = os.WriteFile(filepath.Join(deep, "file.txt"), []byte("x"), 0o644)

	dst := t.TempDir()
	budget := &stagingBudget{bytesLeft: 1 << 20, maxDepth: 2}
	if err := copyDirTree(src, dst, budget); err == nil {
		t.Error("expected depth exceeded error")
	}
}

func TestCopyDirTree_AbortsOnSizeExceeded(t *testing.T) {
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "big.bin"), make([]byte, 1024), 0o644)

	dst := t.TempDir()
	budget := &stagingBudget{bytesLeft: 10, maxDepth: 32}
	if err := copyDirTree(src, dst, budget); err == nil {
		t.Error("expected size exceeded error")
	}
}

func TestCopyDirTree_AbortsOnOutsideRootResolution(t *testing.T) {
	src := t.TempDir()
	outside := t.TempDir()
	_ = os.WriteFile(filepath.Join(outside, "secret.txt"), []byte("secret"), 0o644)

	link := filepath.Join(src, "escape")
	if err := os.Symlink(outside, link); err != nil {
		t.Skip("symlinks not supported:", err)
	}

	dst := t.TempDir()
	budget := &stagingBudget{bytesLeft: 1 << 20, maxDepth: 32}
	_ = copyDirTree(src, dst, budget)

	// Escaped content must never appear in dst.
	if _, err := os.Stat(filepath.Join(dst, "escape", "secret.txt")); err == nil {
		t.Error("escaped file must not appear in destination")
	}
}

func TestCopyDirTree_AllowsExactMaxDepth(t *testing.T) {
	src := t.TempDir()
	// depth 2 from src root: a/b/file.txt → separator count in rel = 2
	nested := filepath.Join(src, "a", "b")
	_ = os.MkdirAll(nested, 0o755)
	_ = os.WriteFile(filepath.Join(nested, "file.txt"), []byte("x"), 0o644)

	dst := t.TempDir()
	budget := &stagingBudget{bytesLeft: 1 << 20, maxDepth: 3}
	if err := copyDirTree(src, dst, budget); err != nil {
		t.Errorf("depth exactly at limit should succeed: %v", err)
	}
}

// ── stageSourceTargets ────────────────────────────────────────────────────────

func TestStageSourceTargets_DisabledWhenSourceRootUnset(t *testing.T) {
	withStagingStubs(t, 1)
	ws := t.TempDir()
	t.Setenv("DECEPTICON_SOURCE_ROOT", "")

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingDisabled {
		t.Errorf("state = %v, want %q", got, stagingDisabled)
	}
}

func TestStageSourceTargets_WaitsForBundleCompleteMarker(t *testing.T) {
	withStagingStubs(t, 3) // only 3 attempts — marker never appears
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()

	// Write the three plan docs but NOT the marker.
	writePlanDocs(t, planDir)
	writeRoE(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	// No migrateEngagementMarker call — simulates an in-progress Soundwave session.
	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q (marker absent should time out)", got, stagingFailed)
	}
	if _, err := os.Stat(filepath.Join(ws, "src")); err == nil {
		t.Error("/workspace/src must not exist when marker never appeared")
	}
}

func TestStageSourceTargets_MarkerTimeoutWritesFailedStatus(t *testing.T) {
	withStagingStubs(t, 2)
	ws := t.TempDir()
	src := t.TempDir()
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)
	// No plan directory, no marker — poll will time out.

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q", got, stagingFailed)
	}
	if errMsg, _ := status["error"].(string); !strings.Contains(errMsg, "timeout") {
		t.Errorf("error message should mention timeout, got %q", errMsg)
	}
}

func TestStageSourceTargets_DetectsStaleMarker(t *testing.T) {
	withStagingStubs(t, 3)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	_ = os.MkdirAll(planDir, 0o755)

	// Write marker FIRST (older mtime), then the docs (newer mtime).
	body, _ := json.Marshal(map[string]interface{}{"schema_version": 1})
	_ = os.WriteFile(filepath.Join(planDir, ".bundle_complete"), body, 0o644)
	time.Sleep(2 * time.Millisecond)
	for _, doc := range []string{"roe.json", "conops.json", "deconfliction.json"} {
		_ = os.WriteFile(filepath.Join(planDir, doc), []byte(`{}`), 0o644)
	}

	src := t.TempDir()
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q (stale marker should produce failed)", got, stagingFailed)
	}
}

func TestStageSourceTargets_StaleMarkerTimeoutWritesFailedStatus(t *testing.T) {
	withStagingStubs(t, 3)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	_ = os.MkdirAll(planDir, 0o755)

	// Same as DetectsStaleMarker — marker is always older than docs.
	body, _ := json.Marshal(map[string]interface{}{"schema_version": 1})
	_ = os.WriteFile(filepath.Join(planDir, ".bundle_complete"), body, 0o644)
	time.Sleep(2 * time.Millisecond)
	for _, doc := range []string{"roe.json", "conops.json", "deconfliction.json"} {
		_ = os.WriteFile(filepath.Join(planDir, doc), []byte(`{}`), 0o644)
	}

	src := t.TempDir()
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q", got, stagingFailed)
	}
	if errMsg, _ := status["error"].(string); !strings.Contains(errMsg, "stale") {
		t.Errorf("error should mention 'stale', got %q", errMsg)
	}
}

func TestMigrateEngagementMarker_WritesMarkerForExistingEngagement(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "hello.txt"), []byte("hi"), 0o644)

	// Set up three plan docs with a proper RoE — no marker (pre-upgrade engagement).
	writePlanDocs(t, planDir)
	writeRoE(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	migrateEngagementMarker(ws)

	if _, err := os.Stat(filepath.Join(planDir, ".bundle_complete")); err != nil {
		t.Error(".bundle_complete should have been written by migration")
	}
}

func TestStageSourceTargets_MigratesOldEngagementOnLaunch(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "hello.txt"), []byte("hi"), 0o644)

	// Pre-upgrade engagement: three plan docs, no marker.
	writePlanDocs(t, planDir)
	writeRoE(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	// Simulate the runStart flow: migrate first, then stage.
	migrateEngagementMarker(ws)
	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("state = %v, want %q", got, stagingStaged)
	}
	if _, err := os.Stat(filepath.Join(ws, "src", "hello.txt")); err != nil {
		t.Error("source file not found in /workspace/src after migration")
	}
}

func TestStageSourceTargets_RetriesOnPartialJSON(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "app.py"), []byte("print('hi')"), 0o644)

	writePlanDocs(t, planDir)
	writeRoE(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	roeFile := filepath.Join(planDir, "roe.json")
	writeBundleMarker(t, planDir)
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	// Intercept readFileFn: return truncated JSON on the very first roe.json read.
	var readCount int32
	origRead := readFileFn
	readFileFn = func(name string) ([]byte, error) {
		if name == roeFile && atomic.AddInt32(&readCount, 1) == 1 {
			return []byte(`{`), nil // truncated
		}
		return origRead(name)
	}
	t.Cleanup(func() { readFileFn = origRead })

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("state = %v, want %q (retry should recover from partial JSON)", got, stagingStaged)
	}
}

func TestStageSourceTargets_SingleSourceFlatLayout(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "main.go"), []byte("package main"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	if _, err := os.Stat(filepath.Join(ws, "src", "main.go")); err != nil {
		t.Error("single source should be staged flat at /workspace/src/main.go")
	}
	// No named subdirectory should exist for a single target.
	entries, _ := os.ReadDir(filepath.Join(ws, "src"))
	for _, e := range entries {
		if e.IsDir() {
			t.Errorf("unexpected subdir %q in flat single-source staging", e.Name())
		}
	}
}

func TestStageSourceTargets_MultiSourcePerTargetSubdirs(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")

	// Both src dirs need to live under the same allowed root.
	allowedRoot := t.TempDir()
	src1 := filepath.Join(allowedRoot, "proj1")
	src2 := filepath.Join(allowedRoot, "proj2")
	_ = os.MkdirAll(src1, 0o755)
	_ = os.MkdirAll(src2, 0o755)
	_ = os.WriteFile(filepath.Join(src1, "a.go"), []byte("package a"), 0o644)
	_ = os.WriteFile(filepath.Join(src2, "b.go"), []byte("package b"), 0o644)

	t.Setenv("DECEPTICON_SOURCE_ROOT", allowedRoot)

	setupPlanBundle(t, planDir, []map[string]string{
		{"target": src1, "type": "source_code"},
		{"target": src2, "type": "source_code"},
	})

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("state = %v, want %q", got, stagingStaged)
	}
	if _, err := os.Stat(filepath.Join(ws, "src", "proj1", "a.go")); err != nil {
		t.Errorf("missing proj1/a.go: %v", err)
	}
	if _, err := os.Stat(filepath.Join(ws, "src", "proj2", "b.go")); err != nil {
		t.Errorf("missing proj2/b.go: %v", err)
	}
}

func TestStageSourceTargets_RejectsTargetOutsideSourceRoot(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")

	allowedRoot := t.TempDir()
	outsideRoot := t.TempDir()
	_ = os.WriteFile(filepath.Join(outsideRoot, "secret.txt"), []byte("secret"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{
		{"target": outsideRoot, "type": "source_code"},
	})
	t.Setenv("DECEPTICON_SOURCE_ROOT", allowedRoot)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q", got, stagingFailed)
	}
}

func TestStageSourceTargets_AllTargetsRejectedWritesFailedNotSkipped(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")

	// Two source entries — one outside root, one missing — both rejected.
	allowedRoot := t.TempDir()
	outsideRoot := t.TempDir()
	_ = os.WriteFile(filepath.Join(outsideRoot, "secret.txt"), []byte("secret"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{
		{"target": outsideRoot, "type": "source_code"},
		{"target": filepath.Join(allowedRoot, "does-not-exist"), "type": "source_code"},
	})
	t.Setenv("DECEPTICON_SOURCE_ROOT", allowedRoot)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q (source was requested but all targets rejected)", got, stagingFailed)
	}
}

func TestStageSourceTargets_AcceptsLocalPathUnderscoreType(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "main.go"), []byte("package main"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{
		{"target": src, "type": "local_path"},
	})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("state = %v, want %q (local_path underscore variant should stage)", got, stagingStaged)
	}
	if _, err := os.Stat(filepath.Join(ws, "src", "main.go")); err != nil {
		t.Errorf("main.go not staged for local_path type: %v", err)
	}
}

func TestCopyDirTree_CumulativeBudgetAcrossSources(t *testing.T) {
	// Verify that the staging budget is shared across multiple sources, not reset
	// per source. We set a 1-byte limit and copy two files — the second copy must
	// fail because the first already exhausted the budget.
	src1 := t.TempDir()
	src2 := t.TempDir()
	_ = os.WriteFile(filepath.Join(src1, "a.go"), []byte("package a"), 0o644)
	_ = os.WriteFile(filepath.Join(src2, "b.go"), []byte("package b"), 0o644)

	dst1 := t.TempDir()
	dst2 := t.TempDir()

	budget := &stagingBudget{bytesLeft: 1, maxDepth: 32}
	if err := copyDirTree(src1, dst1, budget); err == nil {
		t.Fatal("first copy should have exceeded the 1-byte budget")
	}
	if err := copyDirTree(src2, dst2, budget); err == nil {
		t.Fatal("second copy should also fail — budget is shared, not reset")
	}
}

func TestStageSourceTargets_PreservesUnmanagedExistingSrc(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "new.go"), []byte("package x"), 0o644)

	// Pre-create /workspace/src WITHOUT a .decepticon_staged manifest.
	existingSrc := filepath.Join(ws, "src")
	_ = os.MkdirAll(existingSrc, 0o755)
	_ = os.WriteFile(filepath.Join(existingSrc, "manual.go"), []byte("package y"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	if _, err := os.Stat(filepath.Join(existingSrc, "manual.go")); err != nil {
		t.Error("manually created workspace/src was overwritten — should have been preserved")
	}
	if _, err := os.Stat(filepath.Join(existingSrc, "new.go")); err == nil {
		t.Error("staged file appeared in unmanaged workspace/src")
	}
}

func TestStageSourceTargets_WritesTerminalStatusOnSuccess(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "x.py"), []byte("x=1"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("state = %v, want %q", got, stagingStaged)
	}
}

func TestStageSourceTargets_WritesTerminalStatusOnFailure(t *testing.T) {
	withStagingStubs(t, 2)
	ws := t.TempDir()
	src := t.TempDir()
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)
	// No plan dir / marker — will time out.

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingFailed {
		t.Errorf("state = %v, want %q", got, stagingFailed)
	}
}

func TestStageSourceTargets_WritesTerminalStatusOnSkip(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")

	// RoE with no source_code entries.
	setupPlanBundle(t, planDir, []map[string]string{{"target": "example.com", "type": "domain"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", t.TempDir())

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingSkipped {
		t.Errorf("state = %v, want %q", got, stagingSkipped)
	}
}

func TestStageSourceTargets_AcceptsInScopeTargetsKey(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "legacy.go"), []byte("package x"), 0o644)

	writePlanDocs(t, planDir)
	// Use the legacy in_scope_targets key instead of in_scope.
	type entry struct {
		Target string `json:"target"`
		Type   string `json:"type"`
	}
	legacyRoE := struct {
		InScopeTargets []entry `json:"in_scope_targets"`
	}{InScopeTargets: []entry{{Target: src, Type: "source_code"}}}
	data, _ := json.Marshal(legacyRoE)
	_ = os.WriteFile(filepath.Join(planDir, "roe.json"), data, 0o644)
	writeBundleMarker(t, planDir)
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("in_scope_targets backward-compat broken: state = %v, want %q", got, stagingStaged)
	}
	if _, err := os.Stat(filepath.Join(ws, "src", "legacy.go")); err != nil {
		t.Error("legacy.go not found in /workspace/src")
	}
}

func TestStageSourceTargets_AcceptsInScopePrimary(t *testing.T) {
	withStagingStubs(t, 720)
	ws := t.TempDir()
	planDir := filepath.Join(ws, "plan")
	src := t.TempDir()
	_ = os.WriteFile(filepath.Join(src, "main.py"), []byte("pass"), 0o644)

	setupPlanBundle(t, planDir, []map[string]string{{"target": src, "type": "source_code"}})
	t.Setenv("DECEPTICON_SOURCE_ROOT", src)

	stageSourceTargets(ws)

	status := readStatusFile(t, ws)
	if got := status["state"]; got != stagingStaged {
		t.Errorf("in_scope primary key broken: state = %v, want %q", got, stagingStaged)
	}
}

// ── pruneOldStagingArtifacts ──────────────────────────────────────────────────

func TestPruneOldStagingArtifacts_RemovesStaleBackups(t *testing.T) {
	dir := t.TempDir()
	currentRunID := "current123"

	staleDir := filepath.Join(dir, "src.prev-stale456")
	_ = os.MkdirAll(staleDir, 0o755)
	staleTime := time.Now().Add(-(stagingBackupRetention + time.Hour))
	_ = os.Chtimes(staleDir, staleTime, staleTime)

	recentDir := filepath.Join(dir, "src.prev-recent789")
	_ = os.MkdirAll(recentDir, 0o755)

	currentDir := filepath.Join(dir, "src.prev-"+currentRunID)
	_ = os.MkdirAll(currentDir, 0o755)
	_ = os.Chtimes(currentDir, staleTime, staleTime)

	pruneOldStagingArtifacts(dir, currentRunID)

	if _, err := os.Stat(staleDir); err == nil {
		t.Error("stale backup should have been removed")
	}
	if _, err := os.Stat(recentDir); err != nil {
		t.Error("recent backup should have been preserved")
	}
	if _, err := os.Stat(currentDir); err != nil {
		t.Error("current-run backup should have been preserved regardless of age")
	}
}

// ── writeStagingStatus ────────────────────────────────────────────────────────

func TestWriteStagingStatus_ProducesValidJSON(t *testing.T) {
	ws := t.TempDir()
	testErr := fmt.Errorf("something went wrong")
	writeStagingStatus(ws, stagingFailed, []string{"/some/src"}, testErr)

	m := readStatusFile(t, ws)
	if m["state"] != stagingFailed {
		t.Errorf("state = %v, want %q", m["state"], stagingFailed)
	}
	if !strings.Contains(m["error"].(string), "something went wrong") {
		t.Errorf("error field missing or wrong: %v", m["error"])
	}
}
