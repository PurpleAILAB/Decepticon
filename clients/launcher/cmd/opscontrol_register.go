package cmd

import "github.com/PurpleAILAB/Decepticon/clients/launcher/cmd/opscontrol"

// Bridge the opscontrol subcommand tree into the launcher's rootCmd.
// Kept in a separate file so cmd/start.go and cmd/stop.go can import
// the opscontrol package directly (for EnsureRunning / Stop) without
// import cycles.
func init() {
	rootCmd.AddCommand(opscontrol.Cmd)
}
