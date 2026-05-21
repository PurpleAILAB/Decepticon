package platform

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestLinuxDistroParsesPrettyName(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("LinuxDistro only reads /etc/os-release on Linux")
	}
	dir := t.TempDir()
	f := filepath.Join(dir, "os-release")
	content := "NAME=\"Kali GNU/Linux\"\nPRETTY_NAME=\"Kali GNU/Linux Rolling\"\nID=kali\n"
	if err := os.WriteFile(f, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	orig := osReleasePath
	osReleasePath = f
	defer func() { osReleasePath = orig }()

	if got := LinuxDistro(); got != "Kali GNU/Linux Rolling" {
		t.Fatalf("LinuxDistro() = %q, want %q", got, "Kali GNU/Linux Rolling")
	}
}

func TestLinuxDistroMissingFile(t *testing.T) {
	orig := osReleasePath
	osReleasePath = filepath.Join(t.TempDir(), "does-not-exist")
	defer func() { osReleasePath = orig }()

	if got := LinuxDistro(); got != "" {
		t.Fatalf("LinuxDistro() = %q, want empty string", got)
	}
}

func TestDetectDockerFlags(t *testing.T) {
	origProbe := dockerProbe
	defer func() { dockerProbe = origProbe }()

	// Daemon down: info fails, compose still reports available.
	dockerProbe = func(args ...string) bool {
		return len(args) > 0 && args[0] == "compose"
	}
	si := Detect()
	if si.OS != runtime.GOOS || si.Arch != runtime.GOARCH {
		t.Fatalf("Detect() OS/Arch = %s/%s, want %s/%s", si.OS, si.Arch, runtime.GOOS, runtime.GOARCH)
	}
	if si.DockerRunning {
		t.Error("DockerRunning should be false when `docker info` fails")
	}
}

func TestSystemInfoReadyAndHint(t *testing.T) {
	ready := SystemInfo{DockerInstalled: true, DockerRunning: true, ComposeAvailable: true}
	if !ready.Ready() {
		t.Error("Ready() = false for a fully-provisioned host")
	}
	if ready.DockerHint() != "" {
		t.Errorf("DockerHint() = %q, want empty for a ready host", ready.DockerHint())
	}

	noDocker := SystemInfo{OS: "windows"}
	if noDocker.Ready() {
		t.Error("Ready() = true with Docker absent")
	}
	if noDocker.DockerHint() == "" {
		t.Error("DockerHint() should explain how to install Docker")
	}
}

func TestOSLabel(t *testing.T) {
	cases := map[string]SystemInfo{
		"Windows":                {OS: "windows"},
		"macOS":                  {OS: "darwin"},
		"Linux":                  {OS: "linux"},
		"Kali GNU/Linux Rolling": {OS: "linux", Distro: "Kali GNU/Linux Rolling"},
	}
	for want, si := range cases {
		if got := si.OSLabel(); got != want {
			t.Errorf("OSLabel() = %q, want %q", got, want)
		}
	}
}
