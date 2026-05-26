package cmd

import (
	"fmt"
	"os"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var version = "dev"

// ProductName is the binary's user-facing name. Override at build time via
// Go ldflags:
//
//	go build -ldflags="-X 'github.com/PurpleAILAB/Decepticon/clients/launcher/cmd.ProductName=decepticon-mac'"
//
// Pair with -X 'github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config.DefaultHome=.decepticon-mac'
// to also override the data-dir basename. Defaults preserve the historical
// "decepticon" name so unstamped builds behave identically to upstream.
var ProductName = "decepticon"

var rootCmd = &cobra.Command{
	Use:   ProductName,
	Short: "Decepticon — Autonomous Hacking Agent for Red Team",
	Long:  ui.RenderBanner() + "\n" + ui.Dim.Render("Autonomous Hacking Agent for Red Team"),
	CompletionOptions: cobra.CompletionOptions{
		HiddenDefaultCmd: true,
	},
	SilenceUsage:  true,
	SilenceErrors: true,
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		ui.Error(err.Error())
		os.Exit(1)
	}
}

func init() {
	rootCmd.Version = version
	// Route the version banner through ProductName so ldflag-rebuilt
	// binaries (e.g. "decepticon-mac") report their actual name in
	// `--version` instead of a hard-coded "Decepticon".
	rootCmd.SetVersionTemplate(fmt.Sprintf("%s %s\n", ProductName, version))
}
