package cmd

import (
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
		// Clear bash-tool scratch buffers before tearing the stack down so
		// /workspace/.scratch does not accumulate across engagements. Must run
		// while the sandbox is still up; CleanScratch is a no-op otherwise.
		c.CleanScratch()
		if err := c.Down(); err != nil {
			return err
		}
		ui.Success("All services stopped")
		return nil
	},
}

func init() {
	rootCmd.AddCommand(stopCmd)
}
