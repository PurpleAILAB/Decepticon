package cmd

import (
	"fmt"
	"strings"

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
	updateCmd.Flags().BoolVarP(&forceUpdate, "force", "f", false, "Refresh config files and Docker images even if version unchanged")
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
	} else {
		ui.Info("Refreshing configuration files and Docker images...")
	}

	// Load env for branch info
	env := make(map[string]string)
	if config.EnvExists() {
		env, _ = config.LoadEnv(config.EnvPath())
	}
	ref := release.TagName
	if branch := strings.TrimSpace(env["DECEPTICON_BRANCH"]); branch != "" {
		ref = branch
	}

	if hasUpdate {
		// Full upgrade flow — shared with the launch-time interactive
		// prompt so behavior stays consistent between the two paths.
		if err := updater.ApplyUpdate(release, ref); err != nil {
			ui.Warning(err.Error())
		}
	} else {
		// --force: re-sync config + re-pull images without bumping the
		// binary (already on release.TagName).
		ui.Info("Syncing configuration files...")
		// Mirror ApplyUpdate's release/branch split: pass the Release
		// through when ref tracks the tag so the manifest verifies, nil
		// when DECEPTICON_BRANCH is overriding the ref (branch mode).
		syncRelease := release
		if ref != release.TagName && ref != strings.TrimPrefix(release.TagName, "v") {
			syncRelease = nil
		}
		if err := updater.SyncConfigFiles(ref, syncRelease); err != nil {
			ui.Warning("Config sync: " + err.Error())
		}
		c := compose.New()
		targetVersion := strings.TrimPrefix(release.TagName, "v")
		ui.Info("Pulling Docker images (" + targetVersion + ")...")
		if err := c.Pull(targetVersion); err != nil {
			ui.Warning("Image pull: " + err.Error())
		}
	}

	ui.Success("Update complete")
	ui.DimText("Restart Decepticon to use the new version")
	return nil
}
