package compose

import (
	"testing"
)

func TestNew(t *testing.T) {
	t.Setenv("DECEPTICON_HOME", "/tmp/test-decepticon")
	c := New()
	if c.Home != "/tmp/test-decepticon" {
		t.Errorf("Home = %q, want /tmp/test-decepticon", c.Home)
	}
	if c.ComposeFile != "/tmp/test-decepticon/docker-compose.yml" {
		t.Errorf("ComposeFile = %q", c.ComposeFile)
	}
	if c.EnvFile != "/tmp/test-decepticon/.env" {
		t.Errorf("EnvFile = %q", c.EnvFile)
	}
}

func TestAllProfiles(t *testing.T) {
	profiles := AllProfiles()
	if len(profiles) != 4 {
		t.Errorf("AllProfiles() len = %d, want 4 (2 pairs)", len(profiles))
	}
	// Verify pairs
	expected := []string{"--profile", "cli", "--profile", "c2-sliver"}
	for i, v := range expected {
		if profiles[i] != v {
			t.Errorf("profiles[%d] = %q, want %q", i, profiles[i], v)
		}
	}
}

func TestBaseArgs(t *testing.T) {
	c := &Compose{
		Home:        "/test",
		ComposeFile: "/test/docker-compose.yml",
		EnvFile:     "/test/.env",
	}
	args := c.baseArgs()
	if args[0] != "compose" || args[2] != "/test/docker-compose.yml" || args[4] != "/test/.env" {
		t.Errorf("baseArgs = %v", args)
	}
}
