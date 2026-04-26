package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"syscall"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/health"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/updater"
	"github.com/spf13/cobra"
)

var startCmd = &cobra.Command{
	Use:   "start",
	Short: "Start Decepticon services and launch the CLI",
	RunE:  runStart,
}

func init() {
	rootCmd.AddCommand(startCmd)

	// Make start the default command when no subcommand given
	rootCmd.RunE = func(cmd *cobra.Command, args []string) error {
		// If no subcommand, run start
		return runStart(cmd, args)
	}
}

func runStart(cmd *cobra.Command, args []string) error {
	// 1. Check .env exists
	if !config.EnvExists() {
		ui.Warning("No configuration found. Running setup wizard...")
		fmt.Println()
		if err := runOnboard(cmd, nil); err != nil {
			return err
		}
		fmt.Println()
	}

	// 2. Load and validate .env
	env, err := config.LoadEnv(config.EnvPath())
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}
	if err := config.ValidateAuth(env); err != nil {
		return err
	}

	// 2.3. Ensure config files exist (docker-compose.yml, litellm.yaml, workspace)
	home := config.DecepticonHome()
	composePath := filepath.Join(home, "docker-compose.yml")
	if _, err := os.Stat(composePath); os.IsNotExist(err) {
		// Use installed version tag; fall back to branch for dev builds
		ref := "v" + version
		if version == "dev" || version == "" {
			ref = config.Get(env, "DECEPTICON_BRANCH", "main")
		}
		ui.Info("Downloading configuration files...")
		if err := updater.SyncConfigFiles(ref); err != nil {
			return fmt.Errorf("sync config: %w", err)
		}
	}

	// Ensure workspace directory exists
	_ = os.MkdirAll(filepath.Join(home, "workspace"), 0o755)

	// Ensure DECEPTICON_HOME is set in .env (Docker Compose needs absolute path)
	if config.Get(env, "DECEPTICON_HOME", "") == "" {
		env["DECEPTICON_HOME"] = home
		if err := config.AppendEnvLine(config.EnvPath(), "DECEPTICON_HOME", home); err != nil {
			ui.Warning("Could not set DECEPTICON_HOME in .env: " + err.Error())
		}
	}

	// 2.5. Auto-update check
	if updater.CheckAndUpdate(version, env) {
		ui.Info("Restarting with updated binary...")
		return restartSelf()
	}

	// 3. Start services
	c := compose.New()

	ui.Info("Starting Decepticon services...")
	if err := c.Up(compose.Profiles.CLI); err != nil {
		return fmt.Errorf("start services: %w", err)
	}

	// 4. Health checks
	if err := health.WaitForServices(env); err != nil {
		return err
	}

	// 5. Launch CLI
	fmt.Println()
	ui.Info("Launching Decepticon CLI...")

	cliEnv := map[string]string{
		"DECEPTICON_VERSION": version,
	}
	if port := config.Get(env, "WEB_PORT", "3000"); port != "" {
		cliEnv["WEB_PORT"] = port
	}

	// Pass through terminal
	if err := c.RunInteractive(
		[]string{compose.Profiles.CLI},
		"cli",
		cliEnv,
	); err != nil {
		return fmt.Errorf("CLI exited: %w", err)
	}

	// 6. Stop services after CLI exits
	ui.DimText("CLI exited. Stopping services...")
	_ = c.Down()

	// Check if decepticon is running outside docker (dev mode)
	if os.Getenv("DECEPTICON_DEV") == "true" {
		ui.DimText("Dev mode: services kept running")
	}

	return nil
}

// restartSelf re-execs the current binary after a self-update.
func restartSelf() error {
	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("get executable: %w", err)
	}
	return syscall.Exec(execPath, os.Args, os.Environ())
}
