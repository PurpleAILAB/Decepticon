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
	"strings"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
)

// StackName returns the value of DECEPTICON_STACK_NAME, sanitized to
// match the same `[a-z0-9-]{1,32}` shape we accept in compose object
// names. Empty when the user has not opted into a named stack.
//
// Stack-aware paths let two stacks (e.g., the default install and an
// engagement-isolation dogfood install) coexist on the same host
// without colliding socket/PID files or systemd unit names.
func StackName() string {
	name := strings.TrimSpace(os.Getenv("DECEPTICON_STACK_NAME"))
	if name == "" {
		return ""
	}
	// Conservative: only [a-z0-9-]{1,32}. The compose-side container
	// naming already accepts this, and stricter here means a malformed
	// stack name never lands in a unit file or socket path.
	if len(name) > 32 {
		name = name[:32]
	}
	clean := strings.Builder{}
	for _, r := range name {
		switch {
		case r >= 'a' && r <= 'z':
		case r >= '0' && r <= '9':
		case r == '-':
		default:
			r = '-'
		}
		clean.WriteRune(r)
	}
	return clean.String()
}

// stackSuffix returns ".stack2"-style suffix when DECEPTICON_STACK_NAME
// is set, empty otherwise. Used as a filename infix.
func stackSuffix() string {
	if s := StackName(); s != "" {
		return "." + s
	}
	return ""
}

// HostSocketPath returns the host-side path of the opscontrol UDS.
// ADR-0006 §1' specifies /var/run/decepticon-ops.sock for the
// container-internal mount; the host path is rooted under
// $DECEPTICON_HOME so rootless / WSL2 / Mac users do not need write
// access to /var/run. Compose maps the host path → the ADR-mandated
// container path.
//
// Stack-scoped form (DECEPTICON_STACK_NAME=stack2):
//
//	$DECEPTICON_HOME/run/ops.stack2.sock
func HostSocketPath() string {
	return filepath.Join(config.DecepticonHome(), "run", "ops"+stackSuffix()+".sock")
}

// ContainerSocketPath is the ADR-0006 §1' mandated path inside the
// langgraph container. The Python OpsControlClient defaults to it.
// This path is stack-agnostic — each stack gets its own langgraph
// container, so the in-container path can stay constant.
const ContainerSocketPath = "/var/run/decepticon-ops.sock"

// PIDFilePath returns the location of the daemon's PID file. Used by
// `decepticon start` to detect whether a daemon is already running
// and by `decepticon stop` to send SIGTERM.
//
// Stack-scoped form: $DECEPTICON_HOME/run/opscontrol.stack2.pid
func PIDFilePath() string {
	return filepath.Join(config.DecepticonHome(), "run", "opscontrol"+stackSuffix()+".pid")
}

// EnsureRunDir creates $DECEPTICON_HOME/run with mode 0700. Idempotent.
// Used by both the launcher (before spawning the daemon) and the
// daemon itself (before binding the socket).
func EnsureRunDir() error {
	return os.MkdirAll(filepath.Join(config.DecepticonHome(), "run"), 0o700)
}

// ServiceUnitName returns the OS-native service identifier for the
// current stack. systemd uses it as the .service basename; launchd
// uses it as the label. Stack-scoped form: "decepticon-opscontrol-stack2".
func ServiceUnitName() string {
	suffix := StackName()
	if suffix == "" {
		return "decepticon-opscontrol"
	}
	return "decepticon-opscontrol-" + suffix
}
