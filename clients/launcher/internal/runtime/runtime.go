// Package runtime detects which container runtime is available on the
// host (Docker, Podman, or nerdctl) and exposes the binary path plus
// the right "compose" sub-command so the rest of the launcher can call
// `Runtime().Bin compose ...` without caring which one is installed.
//
// Selection order (first hit wins):
//  1. $DECEPTICON_CONTAINER_RUNTIME explicit override ("docker", "podman", "nerdctl")
//  2. `docker` on $PATH and `docker info` succeeds (real Docker, Lima/Colima/Rancher Desktop docker shim)
//  3. `podman` on $PATH and `podman info` succeeds (rootless or rootful Podman 4+)
//  4. `nerdctl` on $PATH and `nerdctl info` succeeds (containerd-native)
//
// On Podman, if a Docker compatibility socket is published, `DOCKER_HOST`
// is auto-set so any nested tooling (kubectl-with-docker-shim,
// playwright/testcontainers, etc.) finds the socket.
package runtime

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

// Runtime is a snapshot of the detected container runtime.
type Runtime struct {
	// Name is the canonical short name: "docker", "podman", "nerdctl".
	Name string
	// Bin is the absolute path of the binary to invoke.
	Bin string
	// ComposeArgs is the prefix to prepend before compose sub-arguments.
	// For Docker this is ["compose"] (Compose v2 plugin). For Podman it
	// is also ["compose"] when Podman 4.4+ ships the built-in compose
	// command, OR ["compose"] via the `podman-compose` Python wrapper
	// (both expose the same `compose -f file up -d` shape).
	ComposeArgs []string
	// DockerHost is the socket the runtime exposes through the Docker API.
	// For native Docker this is unset. For Podman it points at the
	// rootless or rootful Podman socket so other Docker-API consumers
	// keep working.
	DockerHost string
	// Rootless reports whether the runtime is running unprivileged.
	// Affects volume-mount semantics + recommended sysctls.
	Rootless bool
	// Version is the runtime's reported version string ("28.0.1" /
	// "5.2.0" / etc.) for diagnostics.
	Version string
}

// Detect runs the selection rules and returns the chosen runtime. It
// never panics; on failure it returns a zero-value Runtime and an error
// so the caller can render an installation hint.
func Detect() (Runtime, error) {
	// 1. Explicit override
	if forced := strings.ToLower(strings.TrimSpace(os.Getenv("DECEPTICON_CONTAINER_RUNTIME"))); forced != "" {
		switch forced {
		case "docker", "podman", "nerdctl":
			r, err := probe(forced)
			if err != nil {
				return Runtime{}, fmt.Errorf("DECEPTICON_CONTAINER_RUNTIME=%s requested but unusable: %w", forced, err)
			}
			return r, nil
		default:
			return Runtime{}, fmt.Errorf("DECEPTICON_CONTAINER_RUNTIME=%q is not one of docker|podman|nerdctl", forced)
		}
	}

	// 2-4. Autodetect in order of preference
	for _, name := range []string{"docker", "podman", "nerdctl"} {
		if r, err := probe(name); err == nil {
			return r, nil
		}
	}

	return Runtime{}, fmt.Errorf("no container runtime found on PATH (looked for docker, podman, nerdctl)")
}

// probe attempts to use a specific runtime; returns Runtime if it
// responds to `<bin> info`, or an error.
func probe(name string) (Runtime, error) {
	bin, err := exec.LookPath(name)
	if err != nil {
		return Runtime{}, fmt.Errorf("%s not on PATH", name)
	}
	// `<bin> info` succeeds only when the daemon is reachable. Don't
	// blindly accept the binary's presence — Docker Desktop might be
	// installed but stopped.
	if err := exec.Command(bin, "info").Run(); err != nil {
		return Runtime{}, fmt.Errorf("%s installed but daemon not reachable: %w", name, err)
	}

	r := Runtime{Name: name, Bin: bin, ComposeArgs: []string{"compose"}}
	r.Version = versionString(bin)
	r.Rootless = rootless(bin, name)

	switch name {
	case "podman":
		// Try the well-known rootless + rootful socket paths and stick
		// the first existing one into DOCKER_HOST so anything else that
		// speaks the Docker API auto-finds Podman's compatibility socket.
		if sock := podmanSocket(); sock != "" {
			r.DockerHost = "unix://" + sock
		}
		// `podman compose` is built-in from Podman 4.4 onward; older
		// installs need the separate `podman-compose` Python wrapper.
		// Fall back to it only if `podman compose --help` rejects.
		if !hasBuiltinPodmanCompose(bin) {
			if pc, err := exec.LookPath("podman-compose"); err == nil {
				r.Bin = pc
				r.ComposeArgs = nil // podman-compose IS the compose binary
			}
		}
	case "nerdctl":
		// nerdctl's compose sub-command is built-in since 0.16; older
		// builds had a separate `nerdctl-compose`.
	}

	return r, nil
}

// podmanSocket returns the path of an existing Podman API socket, or
// "" if none can be located. Checks rootless ($XDG_RUNTIME_DIR) first,
// then the rootful default.
func podmanSocket() string {
	if xdg := os.Getenv("XDG_RUNTIME_DIR"); xdg != "" {
		p := filepath.Join(xdg, "podman", "podman.sock")
		if fileExists(p) {
			return p
		}
	}
	// Rootless fallback for $XDG_RUNTIME_DIR unset on Linux distros
	// that don't export it for interactive shells.
	if uid := os.Getuid(); uid >= 0 {
		p := filepath.Join("/run", "user", strconv.Itoa(uid), "podman", "podman.sock")
		if fileExists(p) {
			return p
		}
	}
	// Rootful default
	if fileExists("/run/podman/podman.sock") {
		return "/run/podman/podman.sock"
	}
	// macOS Podman Desktop uses a different path; user can override via
	// DECEPTICON_DOCKER_HOST if needed.
	return ""
}

// rootless returns true when the runtime is running without root
// privileges. Docker Desktop on macOS/Windows is "rootless" from the
// host's perspective; the linux Docker daemon defaults to rootful.
func rootless(bin, name string) bool {
	switch name {
	case "podman":
		// `podman info --format {{.Host.Security.Rootless}}` returns
		// "true" or "false". Older Podman doesn't have that key — assume
		// rootless when the binary path is in $HOME (homebrew, nix).
		out, err := exec.Command(bin, "info", "--format", "{{.Host.Security.Rootless}}").Output()
		if err == nil {
			return strings.TrimSpace(string(out)) == "true"
		}
		return strings.HasPrefix(bin, os.Getenv("HOME"))
	case "docker":
		// Linux Docker is rootful unless explicitly configured (dockerd-
		// rootless-setuptool.sh). macOS/Windows Docker Desktop is rootless
		// from the host's perspective.
		if runtime.GOOS == "linux" {
			// `docker info --format {{.SecurityOptions}}` lists "rootless"
			// when the daemon is rootless.
			out, err := exec.Command(bin, "info", "--format", "{{.SecurityOptions}}").Output()
			if err == nil && strings.Contains(string(out), "rootless") {
				return true
			}
			return false
		}
		return true
	case "nerdctl":
		// Same heuristic as podman.
		out, err := exec.Command(bin, "info", "--format", "{{.SecurityOptions}}").Output()
		return err == nil && strings.Contains(string(out), "rootless")
	}
	return false
}

// hasBuiltinPodmanCompose returns true when `podman compose --help`
// exits 0 (i.e. Podman 4.4+ ships compose support inline).
func hasBuiltinPodmanCompose(bin string) bool {
	err := exec.Command(bin, "compose", "--help").Run()
	return err == nil
}

// versionString returns the runtime's reported version, "unknown" on
// failure.
func versionString(bin string) string {
	out, err := exec.Command(bin, "version", "--format", "{{.Server.Version}}").Output()
	if err != nil || len(out) == 0 {
		// Some clients don't expose --format
		out, err = exec.Command(bin, "--version").Output()
		if err != nil {
			return "unknown"
		}
	}
	return strings.TrimSpace(string(out))
}

// fileExists is a small wrapper for sock-path existence checks.
func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// Apply mutates the provided env slice to include any runtime-derived
// env vars (DOCKER_HOST for Podman, etc.). Pure: the input slice is not
// modified — a new slice is returned.
func (r Runtime) Apply(env []string) []string {
	if r.DockerHost == "" {
		return env
	}
	out := make([]string, 0, len(env)+1)
	// Only add DOCKER_HOST if the caller hasn't already set it — let
	// the user's explicit choice win.
	for _, kv := range env {
		if strings.HasPrefix(kv, "DOCKER_HOST=") {
			return env
		}
		out = append(out, kv)
	}
	out = append(out, "DOCKER_HOST="+r.DockerHost)
	return out
}

// String renders a one-line diagnostic for the onboard System Check
// panel and the `decepticon version` output.
func (r Runtime) String() string {
	bits := []string{r.Name}
	if r.Version != "" {
		bits = append(bits, r.Version)
	}
	if r.Rootless {
		bits = append(bits, "rootless")
	}
	if r.DockerHost != "" {
		bits = append(bits, "socket="+r.DockerHost)
	}
	return strings.Join(bits, " · ")
}
