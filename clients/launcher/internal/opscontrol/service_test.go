package opscontrol

import (
	"runtime"
	"strings"
	"testing"
)

func TestNoopManager_Contract(t *testing.T) {
	var m ServiceManager = noopManager{}

	if m.Name() != "none" {
		t.Errorf("Name = %q; want \"none\"", m.Name())
	}
	if m.Available() {
		t.Error("Available() = true; noop must always be unavailable")
	}
	if ok, err := m.Installed(); ok || err != nil {
		t.Errorf("Installed() = (%v,%v); want (false,nil)", ok, err)
	}
	if ok, err := m.Active(); ok || err != nil {
		t.Errorf("Active() = (%v,%v); want (false,nil)", ok, err)
	}
	if err := m.Install(InstallSpec{}); err == nil {
		t.Error("Install on noop must error so callers know the host can't host a managed daemon")
	}
	if err := m.Uninstall(); err != nil {
		t.Errorf("Uninstall on noop must be a clean no-op, got %v", err)
	}
	if err := m.Start(); err == nil {
		t.Error("Start on noop must return ErrNotInstalled equivalent so launcher falls back to spawn")
	}
	if err := m.Stop(); err != nil {
		t.Errorf("Stop on noop must be a clean no-op, got %v", err)
	}
}

func TestDetectServiceManager_ReturnsCorrectShape(t *testing.T) {
	m := DetectServiceManager()
	if m == nil {
		t.Fatal("DetectServiceManager returned nil")
	}
	// Two valid outcomes:
	//   - the platform's manager is wired up and Available() probes
	//     decide whether it's actually usable on this host
	//   - the noop manager is returned for unsupported platforms
	switch runtime.GOOS {
	case "linux":
		if _, ok := m.(*SystemdManager); !ok {
			if _, noop := m.(noopManager); !noop {
				t.Errorf("Linux returned %T; want *SystemdManager or noopManager", m)
			}
		}
	case "darwin":
		if _, ok := m.(*LaunchdManager); !ok {
			if _, noop := m.(noopManager); !noop {
				t.Errorf("Darwin returned %T; want *LaunchdManager or noopManager", m)
			}
		}
	default:
		if _, ok := m.(noopManager); !ok {
			t.Errorf("GOOS=%s returned %T; want noopManager", runtime.GOOS, m)
		}
	}
}

func TestStackName_SanitizesEnv(t *testing.T) {
	cases := []struct{ in, want string }{
		{"", ""},
		{"stack2", "stack2"},
		{"STACK2", "-----2"},          // uppercase replaced; digits preserved
		{"with space", "with-space"},   // space normalized
		{"a$b", "a-b"},                  // special normalized
		{strings.Repeat("x", 64), strings.Repeat("x", 32)}, // truncated
	}
	for _, c := range cases {
		t.Setenv("DECEPTICON_STACK_NAME", c.in)
		got := StackName()
		if got != c.want {
			t.Errorf("StackName(%q) = %q; want %q", c.in, got, c.want)
		}
	}
}
