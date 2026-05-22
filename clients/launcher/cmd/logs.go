package cmd

import (
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/compose"
	"github.com/spf13/cobra"
)

var logsCmd = &cobra.Command{
	Use:   "logs [service]",
	Short: "Follow service logs",
	Long: `Follow service logs. Available services:
  langgraph  (default)
  litellm
  postgres
  neo4j
  sandbox
  web`,
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		service := "langgraph"
		if len(args) > 0 {
			service = args[0]
		}
		return compose.New().Logs(service)
	},
}

func init() {
	rootCmd.AddCommand(logsCmd)
}
