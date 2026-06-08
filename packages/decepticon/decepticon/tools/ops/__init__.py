"""Agent-facing lifecycle tools for ADR-0006's opscontrol daemon.

The orchestrator calls :func:`ops_start` / :func:`ops_stop` /
:func:`ops_status` to bring specialist workloads up and down at
runtime — BHCE for AD, Sliver C2 for post-exploit, etc. Specialist
sub-agents intentionally do not carry these tools (least-privilege
per ADR-0006 §2).
"""

from __future__ import annotations

from decepticon.tools.ops.client import (
    OpsControlClient,
    OpsControlError,
    OpsControlUnreachableError,
)
from decepticon.tools.ops.tools import (
    OPS_TOOLS,
    ops_cleanup_engagement,
    ops_start,
    ops_status,
    ops_stop,
)

__all__ = [
    "OPS_TOOLS",
    "OpsControlClient",
    "OpsControlError",
    "OpsControlUnreachableError",
    "ops_cleanup_engagement",
    "ops_start",
    "ops_status",
    "ops_stop",
]
