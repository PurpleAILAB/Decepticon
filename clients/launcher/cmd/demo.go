package cmd

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/health"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/updater"
	"github.com/spf13/cobra"
)

var demoCmd = &cobra.Command{
	Use:   "demo",
	Short: "Run a demo engagement against Metasploitable 2",
	RunE:  runDemo,
}

func init() {
	rootCmd.AddCommand(demoCmd)
}

func runDemo(cmd *cobra.Command, args []string) error {
	if !config.EnvExists() {
		ui.Warning("No configuration found. Running setup wizard...")
		if err := runOnboard(cmd, nil); err != nil {
			return err
		}
	}

	env, err := config.LoadEnv(config.EnvPath())
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}

	home := config.DecepticonHome()
	demoDir := filepath.Join(home, "workspace", "demo")

	// Download demo plan files
	branch := config.Get(env, "DECEPTICON_BRANCH", "main")
	planDir := filepath.Join(demoDir, "plan")
	if err := os.MkdirAll(planDir, 0o755); err != nil {
		return err
	}

	files := []string{"roe.json", "conops.json", "opplan.json"}
	client := &http.Client{Timeout: 30 * time.Second}
	for _, f := range files {
		dst := filepath.Join(planDir, f)
		if _, err := os.Stat(dst); err == nil {
			continue // Already exists
		}
		url := fmt.Sprintf("%s/%s/demo/plan/%s", updater.RawBaseURL, branch, f)
		ui.Info("Downloading " + f + "...")
		resp, err := client.Get(url)
		if err != nil {
			ui.Warning("Download " + f + ": " + err.Error())
			continue
		}
		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			ui.Warning(fmt.Sprintf("Download %s: HTTP %d", f, resp.StatusCode))
			continue
		}
		data, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			ui.Warning("Read " + f + ": " + err.Error())
			continue
		}
		_ = os.WriteFile(dst, data, 0o644)
	}

	// Create workspace directories
	for _, dir := range []string{"recon", "exploit", "post-exploit"} {
		_ = os.MkdirAll(filepath.Join(demoDir, dir), 0o755)
	}

	// Start services with victims
	c := compose.New()
	ui.Info("Starting services with victim targets...")
	if err := c.Up(compose.Profiles.CLI, compose.Profiles.Victims); err != nil {
		return err
	}

	if err := health.WaitForServices(env); err != nil {
		return err
	}

	// Launch CLI with auto-message
	ui.Info("Launching demo engagement...")
	cliEnv := map[string]string{
		"DECEPTICON_VERSION":         version,
		"DECEPTICON_INITIAL_MESSAGE": "Resume the demo engagement and execute all objectives.",
	}

	if err := c.RunInteractive(
		[]string{compose.Profiles.CLI, compose.Profiles.Victims},
		"cli",
		cliEnv,
	); err != nil {
		return fmt.Errorf("CLI exited: %w", err)
	}

	return nil
}
