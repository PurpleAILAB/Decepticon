package cmd

import (
	"fmt"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/updater"
	"github.com/spf13/cobra"
)

var forceUpdate bool

var updateCmd = &cobra.Command{
	Use:   "update",
	Short: "Check for updates and apply them",
	RunE:  runUpdate,
}

func init() {
	updateCmd.Flags().BoolVarP(&forceUpdate, "force", "f", false, "Force re-pull images even if version unchanged")
	rootCmd.AddCommand(updateCmd)
}

func runUpdate(cmd *cobra.Command, args []string) error {
	ui.Info("Checking for updates...")

	release, err := updater.FetchLatestRelease()
	if err != nil {
		return fmt.Errorf("check updates: %w", err)
	}

	hasUpdate := updater.CompareVersions(version, release.TagName)
	if !hasUpdate && !forceUpdate {
		ui.Success(fmt.Sprintf("Already up to date (%s)", version))
		return nil
	}

	if hasUpdate {
		ui.Info(fmt.Sprintf("Update available: %s → %s", version, release.TagName))
	}

	// Load env for branch info
	env := make(map[string]string)
	if config.EnvExists() {
		env, _ = config.LoadEnv(config.EnvPath())
	}
	branch := config.Get(env, "DECEPTICON_BRANCH", "main")

	// Sync config files
	ui.Info("Syncing configuration files...")
	if err := updater.SyncConfigFiles(branch); err != nil {
		ui.Warning("Config sync: " + err.Error())
	}

	// Pull new images
	c := compose.New()
	targetVersion := release.TagName
	ui.Info("Pulling Docker images (" + targetVersion + ")...")
	if err := c.Pull(targetVersion); err != nil {
		ui.Warning("Image pull: " + err.Error())
	}

	// Self-update binary
	if hasUpdate {
		if err := updater.SelfUpdate(release); err != nil {
			ui.Warning("Binary update: " + err.Error())
		}
		_ = updater.WriteVersion(release.TagName)
	}

	ui.Success("Update complete")
	ui.DimText("Restart Decepticon to use the new version")
	return nil
}
