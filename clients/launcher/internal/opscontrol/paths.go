// Package opscontrol implements the ADR-0006 agent-driven container
// lifecycle daemon and its Backend Protocol.
//
// The daemon is the only process that holds the docker socket; the
// agent calls into it over a Unix-domain socket bind-mounted into
// langgraph (and only langgraph). See docs/adr/0006-agent-driven-container-lifecycle.md.
package opscontrol

import (
	"os"
	"path/filepath"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
)

// HostSocketPath returns the host-side path of the opscontrol UDS.
// ADR-0006 §1' specifies /var/run/decepticon-ops.sock for the
// container-internal mount; the host path is rooted under
// $DECEPTICON_HOME so rootless / WSL2 / Mac users do not need write
// access to /var/run. Compose maps the host path → the ADR-mandated
// container path.
func HostSocketPath() string {
	return filepath.Join(config.DecepticonHome(), "run", "ops.sock")
}

// ContainerSocketPath is the ADR-0006 §1' mandated path inside the
// langgraph container. The Python OpsControlClient defaults to it.
const ContainerSocketPath = "/var/run/decepticon-ops.sock"

// PIDFilePath returns the location of the daemon's PID file. Used by
// `decepticon start` to detect whether a daemon is already running
// and by `decepticon stop` to send SIGTERM.
func PIDFilePath() string {
	return filepath.Join(config.DecepticonHome(), "run", "opscontrol.pid")
}

// EnsureRunDir creates $DECEPTICON_HOME/run with mode 0700. Idempotent.
// Used by both the launcher (before spawning the daemon) and the
// daemon itself (before binding the socket).
func EnsureRunDir() error {
	return os.MkdirAll(filepath.Join(config.DecepticonHome(), "run"), 0o700)
}
