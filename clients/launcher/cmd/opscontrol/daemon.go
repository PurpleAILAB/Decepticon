package opscontrol

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"

	internal "github.com/PurpleAILAB/Decepticon/clients/launcher/internal/opscontrol"
	"github.com/spf13/cobra"
)

var daemonCmd = &cobra.Command{
	Use:   "daemon",
	Short: "Run the opscontrol daemon in the foreground",
	Long: `Runs the opscontrol HTTP server on the Unix domain socket at
$DECEPTICON_HOME/run/ops.sock. Intended to be supervised by
` + "`decepticon start`" + ` (which spawns it detached and writes the
PID file). Operators can also invoke it directly for debugging:

    DECEPTICON_HOME=/tmp/dogfood decepticon opscontrol daemon

ADR-0006 §1' is the authoritative spec.`,
	RunE: runDaemon,
}

func runDaemon(_ *cobra.Command, _ []string) error {
	if err := internal.EnsureRunDir(); err != nil {
		return fmt.Errorf("opscontrol: ensure run dir: %w", err)
	}

	allow, err := internal.LoadAllowlist()
	if err != nil {
		return err
	}

	backend := internal.NewDockerComposeBackend()

	// Wire the launcher's compose override into the backend so
	// docker compose sees the langgraph socket bind-mount that
	// the agent needs to reach this daemon. `make dev` / `make smoke`
	// won't include this file, so they stay daemon-less by design.
	overridePath := filepath.Join(filepath.Dir(backend.ComposeFile), "docker-compose.opscontrol.yml")
	if _, err := os.Stat(overridePath); err == nil {
		backend.ExtraFiles = append(backend.ExtraFiles, overridePath)
	}

	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))
	server := internal.NewServer(backend, allow, logger)

	// Write the PID file so `decepticon stop` knows who to signal.
	// We write our own PID (not the parent shell's) so that a
	// foreground run still places a valid marker.
	pidPath := internal.PIDFilePath()
	if err := os.WriteFile(pidPath, []byte(strconv.Itoa(os.Getpid())), 0o600); err != nil {
		return fmt.Errorf("opscontrol: write pid file: %w", err)
	}
	defer os.Remove(pidPath)

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	socketPath := internal.HostSocketPath()
	logger.Info("opscontrol daemon up",
		"socket", socketPath,
		"backend", backend.Name(),
		"allowlist_size", len(allow.Members()),
	)

	if err := server.Listen(ctx, socketPath); err != nil && err != context.Canceled {
		return err
	}
	logger.Info("opscontrol daemon stopped")
	return nil
}
