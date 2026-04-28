package compose

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
)

// Compose wraps Docker Compose commands for Decepticon services.
type Compose struct {
	Home        string
	ComposeFile string
	EnvFile     string
}

// New creates a Compose instance using the Decepticon home directory.
func New() *Compose {
	home := config.DecepticonHome()
	return &Compose{
		Home:        home,
		ComposeFile: filepath.Join(home, "docker-compose.yml"),
		EnvFile:     filepath.Join(home, ".env"),
	}
}

// Profiles defines available Docker Compose profiles.
var Profiles = struct {
	CLI     string
	Victims string
	C2      string
}{
	CLI:     "cli",
	Victims: "victims",
	C2:      "c2-sliver",
}

// AllProfiles returns all profile flags for complete teardown.
func AllProfiles() []string {
	return []string{
		"--profile", Profiles.CLI,
		"--profile", Profiles.Victims,
		"--profile", Profiles.C2,
	}
}

// baseArgs returns the common compose arguments.
func (c *Compose) baseArgs() []string {
	return []string{"compose", "-f", c.ComposeFile, "--env-file", c.EnvFile}
}

// readVersion returns the installed version from $DECEPTICON_HOME/.version,
// or an empty string if the file is missing or unreadable. The launcher
// (install + auto-update) is the single writer; compose falls back to :latest
// when the marker is absent.
func (c *Compose) readVersion() string {
	data, err := os.ReadFile(filepath.Join(c.Home, ".version"))
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

// composeEnv returns the parent environment with DECEPTICON_VERSION pinned
// from the .version file. docker compose treats the process environment as
// higher precedence than --env-file, so this overrides any stale value the
// user may have written into .env and avoids the silent `:latest` drift
// that occurs when the variable is unset.
func (c *Compose) composeEnv() []string {
	env := os.Environ()
	if v := c.readVersion(); v != "" {
		env = append(env, "DECEPTICON_VERSION="+v)
	}
	return env
}

// run executes a docker compose command and returns its output.
func (c *Compose) run(args []string, interactive bool) error {
	cmdArgs := append([]string{"compose", "-f", c.ComposeFile, "--env-file", c.EnvFile}, args...)
	cmd := exec.Command("docker", cmdArgs...)
	cmd.Env = c.composeEnv()
	if interactive {
		cmd.Stdin = os.Stdin
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	} else {
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	}
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("docker compose %s: %w", strings.Join(args, " "), err)
	}
	return nil
}

// Up starts services in detached mode and blocks until healthchecks pass.
//
// `--wait` (Docker Compose 2.0+) makes `up` block until each service's compose
// healthcheck transitions to healthy, eliminating the need for the launcher to
// re-implement HTTP polling.
//
// `--wait-timeout` is the single user-facing patience knob. Override via
// DECEPTICON_STARTUP_TIMEOUT_SECONDS for slower hardware. Default 600s
// covers most environments after measuring 136s LiteLLM cold start in CI.
func (c *Compose) Up(profiles ...string) error {
	args := []string{}
	for _, p := range profiles {
		args = append(args, "--profile", p)
	}
	args = append(args, "up", "-d", "--no-build", "--wait", "--wait-timeout", startupTimeoutSeconds())
	return c.run(args, false)
}

// startupTimeoutSeconds returns the --wait-timeout value as a string.
// User override via DECEPTICON_STARTUP_TIMEOUT_SECONDS; falls back to 600s.
func startupTimeoutSeconds() string {
	if v := os.Getenv("DECEPTICON_STARTUP_TIMEOUT_SECONDS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return strconv.Itoa(n)
		}
	}
	return "600"
}

// Down stops and removes containers using all profiles for clean teardown.
func (c *Compose) Down() error {
	args := AllProfiles()
	args = append(args, "down")
	return c.run(args, false)
}

// DownAndPurge tears down containers, networks, and named volumes. Used by
// `decepticon remove` so a full uninstall doesn't leave gigabytes of
// postgres/neo4j data behind.
func (c *Compose) DownAndPurge() error {
	args := AllProfiles()
	args = append(args, "down", "--volumes", "--remove-orphans")
	return c.run(args, false)
}

// Pull pulls images for services with a version tag. An explicit version
// argument overrides the .version file (used by the updater right after a
// new release lands). Empty version → fall back to whatever .version says.
func (c *Compose) Pull(version string) error {
	cmd := exec.Command("docker", append(c.baseArgs(), "pull")...)
	if version != "" {
		cmd.Env = append(os.Environ(), "DECEPTICON_VERSION="+version)
	} else {
		cmd.Env = c.composeEnv()
	}
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("docker compose pull: %w", err)
	}
	return nil
}

// Ps shows service status.
func (c *Compose) Ps() error {
	return c.run([]string{"ps"}, false)
}

// Logs follows service logs.
func (c *Compose) Logs(service string) error {
	args := []string{"logs", "-f"}
	if service != "" {
		args = append(args, service)
	}
	return c.run(args, false)
}

// Exec runs a command inside a running service container.
func (c *Compose) Exec(service string, command ...string) error {
	args := append([]string{"exec", "-T", service}, command...)
	return c.run(args, false)
}

// RunInteractive runs a one-off container with stdin attached.
func (c *Compose) RunInteractive(profiles []string, service string, env map[string]string, command ...string) error {
	cmdArgs := c.baseArgs()
	for _, p := range profiles {
		cmdArgs = append(cmdArgs, "--profile", p)
	}
	// Note: --no-build is intentionally absent. `docker compose run` does
	// not accept --no-build (only `up` does); passing it raises
	// "unknown flag: --no-build" on every Compose version. The original
	// concern (OSS users without source triggering a build) doesn't
	// apply here because the cli image is pulled at install time and
	// `run` only builds when the image is missing.
	cmdArgs = append(cmdArgs, "run", "--rm")
	for k, v := range env {
		cmdArgs = append(cmdArgs, "-e", k+"="+v)
	}
	cmdArgs = append(cmdArgs, service)
	cmdArgs = append(cmdArgs, command...)

	cmd := exec.Command("docker", cmdArgs...)
	cmd.Env = c.composeEnv()
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("docker compose run %s: %w", service, err)
	}
	return nil
}

// CleanScratch removes /workspace/.scratch inside the running sandbox.
// Best-effort: silently no-ops when the sandbox is not running so a stale
// scratch directory can be retired without forcing the user to bring the
// stack up just for cleanup.
func (c *Compose) CleanScratch() {
	cmd := exec.Command("docker", "exec", "decepticon-sandbox", "rm", "-rf", "/workspace/.scratch")
	cmd.Stdout = nil
	cmd.Stderr = nil
	_ = cmd.Run()
}

// RemoveOrphanedCLI removes any leftover CLI containers.
func (c *Compose) RemoveOrphanedCLI() {
	// Best-effort cleanup of orphaned CLI containers
	out, err := exec.Command("docker", "ps", "-aq", "--filter", "name=decepticon.*cli").Output()
	if err != nil || len(out) == 0 {
		return
	}
	ids := strings.Fields(strings.TrimSpace(string(out)))
	for _, id := range ids {
		_ = exec.Command("docker", "rm", "-f", id).Run()
	}
}
