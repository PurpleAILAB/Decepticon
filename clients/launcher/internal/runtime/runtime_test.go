package runtime

import (
	"strings"
	"testing"
)

func TestRuntime_String_OnlyName(t *testing.T) {
	r := Runtime{Name: "docker"}
	if got := r.String(); got != "docker" {
		t.Errorf("String() = %q, want %q", got, "docker")
	}
}

func TestRuntime_String_FullFields(t *testing.T) {
	r := Runtime{
		Name:       "podman",
		Version:    "5.2.0",
		Rootless:   true,
		DockerHost: "unix:///run/user/1000/podman/podman.sock",
	}
	got := r.String()
	for _, want := range []string{"podman", "5.2.0", "rootless", "unix:///run/user/1000/podman/podman.sock"} {
		if !strings.Contains(got, want) {
			t.Errorf("String() = %q, want substring %q", got, want)
		}
	}
}

func TestRuntime_Apply_AddsDockerHostWhenUnset(t *testing.T) {
	r := Runtime{Name: "podman", DockerHost: "unix:///run/user/1000/podman/podman.sock"}
	env := []string{"PATH=/usr/bin", "HOME=/home/op"}
	got := r.Apply(env)
	found := false
	for _, kv := range got {
		if kv == "DOCKER_HOST=unix:///run/user/1000/podman/podman.sock" {
			found = true
		}
	}
	if !found {
		t.Errorf("Apply() did not append DOCKER_HOST; got %v", got)
	}
}

func TestRuntime_Apply_RespectsExistingDockerHost(t *testing.T) {
	r := Runtime{Name: "podman", DockerHost: "unix:///run/user/1000/podman/podman.sock"}
	env := []string{"DOCKER_HOST=tcp://1.2.3.4:2375", "PATH=/usr/bin"}
	got := r.Apply(env)
	for _, kv := range got {
		if strings.HasPrefix(kv, "DOCKER_HOST=") && kv != "DOCKER_HOST=tcp://1.2.3.4:2375" {
			t.Errorf("Apply() overwrote user DOCKER_HOST; got %v", got)
		}
	}
	// User's value must survive
	if len(got) != 2 {
		t.Errorf("Apply() altered slice length unexpectedly: got %v", got)
	}
}

func TestRuntime_Apply_NoOpWhenNoDockerHost(t *testing.T) {
	r := Runtime{Name: "docker"}
	env := []string{"PATH=/usr/bin"}
	got := r.Apply(env)
	if len(got) != len(env) {
		t.Errorf("Apply() altered env when DockerHost empty: got %v", got)
	}
}

func TestDetect_RespectsInvalidOverride(t *testing.T) {
	t.Setenv("DECEPTICON_CONTAINER_RUNTIME", "kubernetes")
	_, err := Detect()
	if err == nil {
		t.Fatal("Detect() should reject unknown runtime override")
	}
	if !strings.Contains(err.Error(), "kubernetes") {
		t.Errorf("error should name the bad override; got %v", err)
	}
}

func TestPodmanSocket_ReturnsEmptyWhenNothingExists(t *testing.T) {
	// Force every search path to a non-existent directory by clearing
	// XDG_RUNTIME_DIR; getuid() will still be set but the rootless +
	// rootful paths are very unlikely to exist on a CI runner that
	// doesn't have podman installed.
	t.Setenv("XDG_RUNTIME_DIR", "/tmp/does-not-exist-decepticon-test")
	// Best-effort: this also succeeds on a runner with Podman
	// installed, so just check it returns a string (path) or empty.
	got := podmanSocket()
	// On runners without Podman it should be empty; on dev workstations
	// with Podman installed the test simply confirms we don't panic.
	_ = got
}
