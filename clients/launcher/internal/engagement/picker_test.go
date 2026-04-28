package engagement

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestScanReady_NoWorkspace(t *testing.T) {
	dir := t.TempDir()
	got, err := ScanReady(dir)
	if err != nil {
		t.Fatalf("ScanReady: %v", err)
	}
	if len(got) != 0 {
		t.Errorf("expected empty result, got %v", got)
	}
}

func TestScanReady_OnlyDirsWithFullBundle(t *testing.T) {
	home := t.TempDir()
	mkBundle := func(slug string, partial bool) {
		plan := filepath.Join(home, "workspace", slug, "plan")
		if err := os.MkdirAll(plan, 0o755); err != nil {
			t.Fatal(err)
		}
		write := func(name string) {
			if err := os.WriteFile(filepath.Join(plan, name), []byte("{}"), 0o600); err != nil {
				t.Fatal(err)
			}
		}
		write("roe.json")
		if partial {
			return
		}
		write("conops.json")
		write("deconfliction.json")
	}

	mkBundle("alpha", false)   // ready
	mkBundle("bravo", true)    // partial — missing two
	mkBundle("charlie", false) // ready

	// Add a stray non-engagement directory.
	if err := os.MkdirAll(filepath.Join(home, "workspace", "junk"), 0o755); err != nil {
		t.Fatal(err)
	}

	got, err := ScanReady(home)
	if err != nil {
		t.Fatalf("ScanReady: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 ready, got %d (%v)", len(got), got)
	}
	seen := map[string]bool{got[0]: true, got[1]: true}
	if !seen["alpha"] || !seen["charlie"] {
		t.Errorf("expected alpha+charlie, got %v", got)
	}
}

func TestScanReady_OrdersByMostRecentRoeMtime(t *testing.T) {
	home := t.TempDir()
	mkReady := func(slug string, mtime time.Time) {
		plan := filepath.Join(home, "workspace", slug, "plan")
		if err := os.MkdirAll(plan, 0o755); err != nil {
			t.Fatal(err)
		}
		for _, n := range []string{"roe.json", "conops.json", "deconfliction.json"} {
			path := filepath.Join(plan, n)
			if err := os.WriteFile(path, []byte("{}"), 0o600); err != nil {
				t.Fatal(err)
			}
			if n == "roe.json" {
				if err := os.Chtimes(path, mtime, mtime); err != nil {
					t.Fatal(err)
				}
			}
		}
	}

	now := time.Now()
	mkReady("oldest", now.Add(-2*time.Hour))
	mkReady("newest", now)
	mkReady("mid", now.Add(-1*time.Hour))

	got, err := ScanReady(home)
	if err != nil {
		t.Fatalf("ScanReady: %v", err)
	}
	want := []string{"newest", "mid", "oldest"}
	if len(got) != len(want) {
		t.Fatalf("expected %v, got %v", want, got)
	}
	for i, slug := range want {
		if got[i] != slug {
			t.Errorf("position %d: expected %q, got %q (full: %v)", i, slug, got[i], got)
		}
	}
}
