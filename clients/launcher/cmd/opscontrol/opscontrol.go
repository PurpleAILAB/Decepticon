// Package opscontrol exposes the `decepticon opscontrol` Cobra
// command tree. The daemon's actual HTTP server + Backend live in
// `internal/opscontrol`; this package wires them into the launcher
// CLI so the same binary that onboards a user also runs the
// lifecycle daemon.
//
// ADR-0006 §1' specifies a host-binary daemon as the only process
// that touches the docker socket. Embedding it in the launcher rather
// than shipping a second binary keeps the OSS release matrix
// unchanged (single `decepticon` artifact) and onboarding simple.
package opscontrol

import "github.com/spf13/cobra"

// Cmd is the root of the opscontrol command tree. The launcher's
// `cmd/root.go` adds it to rootCmd in its init.
var Cmd = &cobra.Command{
	Use:   "opscontrol",
	Short: "Manage the agent-driven workload lifecycle daemon (ADR-0006)",
	Long: `opscontrol owns the docker socket on behalf of the agent so the
orchestrator can spawn domain-specific workloads (BHCE for AD,
Sliver C2 for post-exploit, etc.) at runtime rather than booting
the entire stack up front.

The daemon HTTP API is reachable only over a Unix domain socket
bind-mounted into the langgraph container. See
docs/adr/0006-agent-driven-container-lifecycle.md.`,
}

func init() {
	Cmd.AddCommand(daemonCmd)
}
