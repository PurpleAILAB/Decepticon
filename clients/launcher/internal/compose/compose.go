package compose

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
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

// run executes a docker compose command and returns its output.
func (c *Compose) run(args []string, interactive bool) error {
	cmdArgs := append([]string{"compose", "-f", c.ComposeFile, "--env-file", c.EnvFile}, args...)
	cmd := exec.Command("docker", cmdArgs...)
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

// Up starts services in detached mode with the given profiles.
func (c *Compose) Up(profiles ...string) error {
	args := []string{}
	for _, p := range profiles {
		args = append(args, "--profile", p)
	}
	args = append(args, "up", "-d", "--no-build")
	return c.run(args, false)
}

// Down stops and removes containers using all profiles for clean teardown.
func (c *Compose) Down() error {
	args := AllProfiles()
	args = append(args, "down")
	return c.run(args, false)
}

// Pull pulls images for services with a version tag.
func (c *Compose) Pull(version string) error {
	cmd := exec.Command("docker", append(c.baseArgs(), "pull")...)
	cmd.Env = append(os.Environ(), "DECEPTICON_VERSION="+version)
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
	cmdArgs = append(cmdArgs, "run", "--rm")
	for k, v := range env {
		cmdArgs = append(cmdArgs, "-e", k+"="+v)
	}
	cmdArgs = append(cmdArgs, service)
	cmdArgs = append(cmdArgs, command...)

	cmd := exec.Command("docker", cmdArgs...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("docker compose run %s: %w", service, err)
	}
	return nil
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
