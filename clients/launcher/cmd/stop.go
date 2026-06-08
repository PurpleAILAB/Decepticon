package cmd

import (
	"github.com/PurpleAILAB/Decepticon/clients/launcher/cmd/opscontrol"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var stopCmd = &cobra.Command{
	Use:   "stop",
	Short: "Stop all Decepticon services",
	RunE: func(cmd *cobra.Command, args []string) error {
		c := compose.New()
		ui.Info("Stopping Decepticon services...")
		c.RemoveOrphanedCLI()
		// Clear legacy root-level scratch/session buffers before tearing the
		// stack down. Current runs keep these under engagement workspaces.
		c.CleanScratch()
		if err := c.Down(); err != nil {
			return err
		}
		// Tear down the opscontrol daemon after compose so any
		// workload it owned has already been removed by `compose down`.
		// Non-fatal: a never-started daemon is a no-op here.
		if err := opscontrol.Stop(); err != nil {
			ui.Warning("opscontrol stop: " + err.Error())
		}
		ui.Success("All services stopped")
		return nil
	},
}

func init() {
	rootCmd.AddCommand(stopCmd)
}
