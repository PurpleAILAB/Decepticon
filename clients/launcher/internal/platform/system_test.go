package platform

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
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

// TestDockerHint_ComposeMissing exercises the Compose-v2-not-installed
// branch — Docker engine itself is running but the `docker compose`
// subcommand fails. Common on RHEL/CentOS where docker-compose v1 is
// shipped as a separate package.
func TestDockerHint_ComposeMissing(t *testing.T) {
	si := SystemInfo{
		OS:               "linux",
		DockerInstalled:  true,
		DockerRunning:    true,
		ComposeAvailable: false,
	}
	if si.Ready() {
		t.Error("Ready() should be false when Compose v2 is missing")
	}
	hint := si.DockerHint()
	if hint == "" {
		t.Fatal("DockerHint() should return non-empty when Compose v2 is missing")
	}
	if !contains(hint, "Compose v2") {
		t.Errorf("DockerHint() = %q, want mention of 'Compose v2'", hint)
	}
}

// TestDockerHint_LinuxDaemonStopped covers the Linux-non-WSL branch
// that points the user at `systemctl start docker` instead of Docker
// Desktop. Without this case, the launcher would show the macOS / WSL
// "Start Docker Desktop" hint to a Kali / Debian / Arch user — wrong UX.
func TestDockerHint_LinuxDaemonStopped(t *testing.T) {
	si := SystemInfo{
		OS:              "linux",
		DockerInstalled: true,
		DockerRunning:   false,
		IsWSL:           false,
	}
	hint := si.DockerHint()
	if !contains(hint, "systemctl start docker") {
		t.Errorf("DockerHint() = %q, want mention of `systemctl start docker` for native Linux", hint)
	}
}

// TestDockerHint_WSLDaemonStopped covers the WSL-on-Windows branch
// where the right remediation is "Start Docker Desktop on Windows",
// not `systemctl` (which won't work — WSL2 typically doesn't run
// systemd, and Docker Desktop integration is the supported path).
func TestDockerHint_WSLDaemonStopped(t *testing.T) {
	si := SystemInfo{
		OS:              "linux",
		DockerInstalled: true,
		DockerRunning:   false,
		IsWSL:           true,
	}
	hint := si.DockerHint()
	if contains(hint, "systemctl start docker") {
		t.Errorf("DockerHint() = %q, must NOT suggest systemctl when running under WSL", hint)
	}
	if !contains(hint, "Docker Desktop") {
		t.Errorf("DockerHint() = %q, want mention of 'Docker Desktop' for WSL host", hint)
	}
}

// TestDockerHint_PerOSInstallURL verifies the install URL points at the
// correct vendor docs per OS. A Windows user being told to install
// Docker Engine (Linux package) is a UX failure that wastes ~10
// minutes of operator time on first run.
func TestDockerHint_PerOSInstallURL(t *testing.T) {
	cases := []struct {
		os       string
		wantPart string
	}{
		{"windows", "windows-install"},
		{"darwin", "mac-install"},
		{"linux", "engine/install"},
	}
	for _, c := range cases {
		hint := SystemInfo{OS: c.os}.DockerHint()
		if !contains(hint, c.wantPart) {
			t.Errorf("OS=%s: DockerHint() = %q, want substring %q", c.os, hint, c.wantPart)
		}
	}
}

// TestDetect_ComposeAvailableWhenDockerInstalled checks the happy path
// where both `docker info` and `docker compose version` succeed; the
// existing TestDetectDockerFlags only exercises the failure branch.
func TestDetect_ComposeAvailableWhenDockerInstalled(t *testing.T) {
	origProbe := dockerProbe
	defer func() { dockerProbe = origProbe }()

	dockerProbe = func(args ...string) bool { return true }
	si := Detect()
	// Detect() only sets compose/running flags when the `docker` binary
	// is on PATH. On a runner without docker installed, these will be
	// false regardless of the probe stub. Skip in that case rather than
	// asserting an environment-dependent invariant.
	if !si.DockerInstalled {
		t.Skip("docker binary not on PATH for this runner")
	}
	if !si.DockerRunning {
		t.Error("DockerRunning should be true when info probe returns true")
	}
	if !si.ComposeAvailable {
		t.Error("ComposeAvailable should be true when compose probe returns true")
	}
}

// TestLinuxDistroIgnoresQuotedValues exercises the unquoting logic so
// distros that don't quote PRETTY_NAME (Arch, some Debian rolling
// builds) parse correctly.
func TestLinuxDistroIgnoresQuotedValues(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("LinuxDistro only reads /etc/os-release on Linux")
	}
	dir := t.TempDir()
	f := filepath.Join(dir, "os-release")
	content := "PRETTY_NAME=Arch Linux\nID=arch\n"
	if err := os.WriteFile(f, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	orig := osReleasePath
	osReleasePath = f
	defer func() { osReleasePath = orig }()

	if got := LinuxDistro(); got != "Arch Linux" {
		t.Errorf("LinuxDistro() = %q, want %q (unquoted PRETTY_NAME)", got, "Arch Linux")
	}
}

// contains wraps strings.Contains as a tiny test helper. Kept named
// the same as Go's builtin map check to read naturally in assertions.
func contains(haystack, needle string) bool {
	return strings.Contains(haystack, needle)
}
