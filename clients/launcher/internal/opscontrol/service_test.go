package opscontrol

import (
	"os"
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

func TestComposeProjectName_EnvOverrideWins(t *testing.T) {
	t.Setenv("DECEPTICON_STACK_NAME", "stack2")
	t.Setenv(ComposeProjectEnv, "decepticon-saas-dev")
	if got := ComposeProjectName(); got != "decepticon-saas-dev" {
		t.Errorf("ComposeProjectName = %q; want explicit override %q", got, "decepticon-saas-dev")
	}
}

func TestComposeProjectName_FallsBackToStackName(t *testing.T) {
	t.Setenv(ComposeProjectEnv, "")
	t.Setenv("DECEPTICON_STACK_NAME", "stack2")
	if got := ComposeProjectName(); got != "decepticon-stack2" {
		t.Errorf("ComposeProjectName = %q; want fallback %q", got, "decepticon-stack2")
	}
	t.Setenv("DECEPTICON_STACK_NAME", "")
	if got := ComposeProjectName(); got != "decepticon" {
		t.Errorf("ComposeProjectName = %q; want fallback %q", got, "decepticon")
	}
}

func TestComposeCommandEnv_NormalizesUnsetVars(t *testing.T) {
	os.Unsetenv("DECEPTICON_STACK_NAME")
	os.Unsetenv(ComposeProjectEnv)
	env := ComposeCommandEnv()
	var sawStack, sawProject bool
	for _, e := range env {
		if e == "DECEPTICON_STACK_NAME=" {
			sawStack = true
		}
		if e == ComposeProjectEnv+"=" {
			sawProject = true
		}
	}
	if !sawStack {
		t.Error("ComposeCommandEnv must inject empty DECEPTICON_STACK_NAME so compose's --env-file does not silently disagree with the launcher")
	}
	if !sawProject {
		t.Error("ComposeCommandEnv must inject empty DECEPTICON_COMPOSE_PROJECT for the same reason")
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
