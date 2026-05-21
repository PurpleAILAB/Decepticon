package platform

import (
	"os"
	"os/exec"
	"runtime"
	"strings"
)

// osReleasePath is overridable in tests. The default reads the
// freedesktop.org /etc/os-release file present on every modern Linux
// distribution (Debian, Kali, Arch, BlackArch, Parrot, Raspberry Pi OS).
var osReleasePath = "/etc/os-release"

// dockerProbe runs a `docker` subcommand and reports whether it
// succeeded. Overridable in tests so the host's real Docker state does
// not make the suite non-deterministic.
var dockerProbe = func(args ...string) bool {
	return exec.Command("docker", args...).Run() == nil
}

// SystemInfo is a one-shot snapshot of the host environment. `decepticon
// onboard` renders it so the user can confirm — before configuring any
// credentials — that the machine they are on is actually able to run the
// Docker stack, on whichever OS/architecture they happen to be using.
type SystemInfo struct {
	OS               string // GOOS: "windows", "darwin", "linux"
	Arch             string // GOARCH: "amd64", "arm64", ...
	Distro           string // Linux distro pretty-name; "" off Linux
	IsWSL            bool   // running inside Windows Subsystem for Linux
	DockerInstalled  bool   // a `docker` binary is on PATH
	DockerRunning    bool   // the Docker daemon answers `docker info`
	ComposeAvailable bool   // Docker Compose v2 (`docker compose`) works
}

// LinuxDistro returns the human-readable distribution name from
// /etc/os-release (PRETTY_NAME), e.g. "Kali GNU/Linux Rolling" or
// "Debian GNU/Linux 12 (bookworm)". Returns "" on non-Linux hosts or
// when the file cannot be read/parsed.
func LinuxDistro() string {
	if runtime.GOOS != "linux" {
		return ""
	}
	data, err := os.ReadFile(osReleasePath)
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(data), "\n") {
		if v, ok := strings.CutPrefix(strings.TrimSpace(line), "PRETTY_NAME="); ok {
			return strings.Trim(v, `"`)
		}
	}
	return ""
}

// Detect probes the host environment once. The Docker checks shell out
// to the `docker` CLI; each is independently guarded so a missing binary
// or stopped daemon degrades to a false flag rather than an error.
func Detect() SystemInfo {
	si := SystemInfo{
		OS:     runtime.GOOS,
		Arch:   runtime.GOARCH,
		Distro: LinuxDistro(),
		IsWSL:  IsWSL(),
	}
	if _, err := exec.LookPath("docker"); err == nil {
		si.DockerInstalled = true
		si.DockerRunning = dockerProbe("info")
		si.ComposeAvailable = dockerProbe("compose", "version")
	}
	return si
}

// OSLabel returns a friendly OS name for display.
func (si SystemInfo) OSLabel() string {
	switch si.OS {
	case "windows":
		return "Windows"
	case "darwin":
		return "macOS"
	case "linux":
		if si.Distro != "" {
			return si.Distro
		}
		return "Linux"
	default:
		return si.OS
	}
}

// Ready reports whether the host can run the Decepticon stack right now
// (Docker installed, daemon up, Compose v2 present).
func (si SystemInfo) Ready() bool {
	return si.DockerInstalled && si.DockerRunning && si.ComposeAvailable
}

// DockerHint returns OS-appropriate remediation text when Docker is not
// usable, or "" when everything is ready.
func (si SystemInfo) DockerHint() string {
	if !si.DockerInstalled {
		switch si.OS {
		case "windows":
			return "Docker not found — install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
		case "darwin":
			return "Docker not found — install Docker Desktop: https://docs.docker.com/desktop/install/mac-install/"
		default:
			return "Docker not found — install Docker Engine: https://docs.docker.com/engine/install/"
		}
	}
	if !si.DockerRunning {
		if si.OS == "linux" && !si.IsWSL {
			return "Docker is installed but the daemon is not running — start it with: sudo systemctl start docker"
		}
		return "Docker is installed but not running — start Docker Desktop, then re-run onboarding."
	}
	if !si.ComposeAvailable {
		return "Docker Compose v2 is missing — install the compose plugin: https://docs.docker.com/compose/install/"
	}
	return ""
}
