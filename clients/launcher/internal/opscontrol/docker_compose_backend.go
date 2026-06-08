package opscontrol

import (
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
)

// DockerComposeBackend shells out to `docker compose` to fulfill the
// Backend Protocol. ADR-0006 §5' chose shell-out over the docker SDK
// so profile resolution (depends_on chains, healthchecks, wait
// semantics) stays in upstream compose. This keeps a non-trivial
// resolver out of our codebase.
type DockerComposeBackend struct {
	// ComposeFile + EnvFile + (optional) extra files combine into the
	// `-f`/`--env-file` prefix every compose call uses. Defaults from
	// $DECEPTICON_HOME.
	ComposeFile string
	EnvFile     string
	ExtraFiles  []string
	// WaitTimeoutSeconds caps the `--wait` flag on `up`. ADR-0006
	// notes BHCE cold-start is ~30s; we default to 180s to absorb
	// goose migrations and dawgs index build.
	WaitTimeoutSeconds int
}

// NewDockerComposeBackend constructs a backend with the launcher's
// standard $DECEPTICON_HOME paths.
func NewDockerComposeBackend() *DockerComposeBackend {
	home := config.DecepticonHome()
	return &DockerComposeBackend{
		ComposeFile:        filepath.Join(home, "docker-compose.yml"),
		EnvFile:            filepath.Join(home, ".env"),
		WaitTimeoutSeconds: 180,
	}
}

func (b *DockerComposeBackend) Name() string { return "docker-compose" }

// baseArgs returns the shared prefix for every compose call. The
// `-p PROJECT` flag is explicit and shares the value with the
// launcher's compose.baseArgs() through ComposeProjectName(), so both
// sides own the same compose project — that guarantees the daemon
// can adopt containers the launcher already created (and vice versa)
// instead of getting a "container_name already in use" conflict from
// docker when the two project names accidentally drift apart.
func (b *DockerComposeBackend) baseArgs() []string {
	args := []string{
		"compose",
		"-p", ComposeProjectName(),
		"-f", b.ComposeFile,
		"--env-file", b.EnvFile,
	}
	for _, f := range b.ExtraFiles {
		args = append(args, "-f", f)
	}
	return args
}

// Start runs `docker compose --profile <workload> up -d --wait`. The
// caller (server.go) has already taken the per-workload mutex, so
// concurrent calls on the same workload are serialized.
//
// `--no-recreate` is load-bearing for the agent-driven flow. Without
// it, compose's incremental model rebuilds the merged config every
// time the daemon adds a profile on top of what the launcher already
// activated -- the resulting per-service config-hash differs from
// what the launcher wrote, and compose tags every live container
// "Recreate" mid-engagement. Workload spawn is purely ADDITIVE
// (langgraph / litellm / sandbox were correctly running BEFORE
// ops_start; they must keep running AFTER). `--no-recreate` tells
// compose to skip the hash diff and only create services the
// requested profile activates that are not already running.
func (b *DockerComposeBackend) Start(ctx context.Context, workload string, _ string) (Handle, error) {
	args := append(b.baseArgs(),
		"--profile", workload,
		"up", "-d", "--no-build", "--no-recreate", "--wait",
		"--wait-timeout", fmt.Sprintf("%d", b.WaitTimeoutSeconds),
	)
	cmd := exec.CommandContext(ctx, "docker", args...)
	cmd.Env = ComposeCommandEnv()
	out, err := cmd.CombinedOutput()
	if err != nil {
		return Handle{}, fmt.Errorf("compose up --profile %s: %w: %s", workload, err, strings.TrimSpace(string(out)))
	}
	return Handle{Workload: workload, State: StateRunning}, nil
}

// Stop runs `docker compose --profile <workload> stop`. We deliberately
// don't `down` because that removes containers belonging to other
// profiles that share the project (e.g., a `down` triggered by
// ops_stop("ad") would also nuke the postgres container).
func (b *DockerComposeBackend) Stop(ctx context.Context, workload string) error {
	args := append(b.baseArgs(), "--profile", workload, "stop")
	cmd := exec.CommandContext(ctx, "docker", args...)
	cmd.Env = ComposeCommandEnv()
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("compose stop --profile %s: %w: %s", workload, err, strings.TrimSpace(string(out)))
	}
	return nil
}

// List delegates to the in-memory registry. ADR-0006 §5' allows the
// backend to be the source of truth, but a `docker compose ps` round
// trip for every `ops_status()` call is wasteful when the daemon
// already owns the lifecycle transitions that mutate state. The
// registry is the source of truth; backend.List exists so future
// non-daemon-driven backends (Kubernetes pod watch) can override it.
func (b *DockerComposeBackend) List(_ context.Context) ([]WorkloadStatus, error) {
	// The server passes its own registry snapshot in; this backend
	// returns nil to mean "use the registry".
	return nil, nil
}
