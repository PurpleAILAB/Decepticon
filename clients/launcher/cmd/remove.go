package cmd

import (
	"bufio"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"charm.land/huh/v2"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var (
	removeYes bool
)

var removeCmd = &cobra.Command{
	Use:     "remove",
	Aliases: []string{"uninstall"},
	Short:   "Uninstall Decepticon completely",
	RunE:    runRemove,
}

func init() {
	removeCmd.Flags().BoolVar(&removeYes, "yes", false, "Skip confirmation prompts")
	rootCmd.AddCommand(removeCmd)
}

func runRemove(cmd *cobra.Command, args []string) error {
	if !removeYes {
		var confirm bool
		form := huh.NewForm(
			huh.NewGroup(
				huh.NewConfirm().
					Title("Remove Decepticon?").
					Description("This will stop all services, remove Docker images, and delete configuration.").
					Affirmative("Yes, remove").
					Negative("Cancel").
					Value(&confirm),
			),
		)
		if err := form.Run(); err != nil || !confirm {
			ui.Info("Removal cancelled")
			return nil
		}
	}

	home := config.DecepticonHome()
	c := compose.New()

	// Phase 1: Stop containers
	ui.Info("Stopping services...")
	_ = c.Down()
	c.RemoveOrphanedCLI()

	// Phase 2: Remove Docker images
	ui.Info("Removing Docker images...")
	out, err := exec.Command("docker", "images", "--format", "{{.Repository}}:{{.Tag}}", "--filter", "reference=*decepticon*").Output()
	if err == nil {
		for _, img := range strings.Fields(strings.TrimSpace(string(out))) {
			_ = exec.Command("docker", "rmi", "-f", img).Run()
		}
	}

	// Phase 3: Remove config directory
	var preserveWorkspace bool
	if !removeYes {
		form := huh.NewForm(
			huh.NewGroup(
				huh.NewConfirm().
					Title("Preserve workspace data?").
					Description(filepath.Join(home, "workspace")).
					Affirmative("Yes, keep my data").
					Negative("No, delete everything").
					Value(&preserveWorkspace),
			),
		)
		_ = form.Run()
	}

	userHome, _ := os.UserHomeDir()
	backupDir := filepath.Join(userHome, "decepticon-workspace-backup")

	if preserveWorkspace {
		wsDir := filepath.Join(home, "workspace")
		ui.Info("Backing up workspace to " + backupDir)
		if err := os.Rename(wsDir, backupDir); err != nil {
			ui.Warning("Backup failed: " + err.Error())
		}
	}

	ui.Info("Removing " + home + "...")
	if err := os.RemoveAll(home); err != nil {
		ui.Error("Failed to remove " + home + ": " + err.Error())
		ui.DimText("Run manually: sudo rm -rf " + home)
	}

	// Phase 4: Remove launcher binary
	execPath, _ := os.Executable()
	ui.Info("Removing launcher binary...")
	_ = os.Remove(execPath)

	// Phase 5: Clean PATH from shell rc files
	cleanShellRC()

	ui.Success("Decepticon has been removed")
	if preserveWorkspace {
		ui.DimText("Workspace data preserved at " + backupDir)
	}
	return nil
}

// cleanShellRC removes PATH additions from shell config files.
func cleanShellRC() {
	home, err := os.UserHomeDir()
	if err != nil {
		return
	}

	rcFiles := []string{
		filepath.Join(home, ".bashrc"),
		filepath.Join(home, ".profile"),
		filepath.Join(home, ".zshrc"),
		filepath.Join(home, ".config", "fish", "config.fish"),
	}

	for _, rc := range rcFiles {
		cleanPathFromFile(rc)
	}
}

func cleanPathFromFile(path string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()

	var lines []string
	changed := false
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.Contains(line, ".local/bin") && strings.Contains(line, "decepticon") {
			changed = true
			continue
		}
		lines = append(lines, line)
	}

	if changed {
		_ = os.WriteFile(path, []byte(strings.Join(lines, "\n")+"\n"), 0o644)
	}
}
