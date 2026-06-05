"""Agent-facing LangChain ``@tool`` surface for the ops-control sidecar.

ADR: docs/adr/0006-agent-driven-container-lifecycle.md

Only the orchestrator agent (``decepticon``) is expected to import
this surface.  Specialist sub-agents must not see it — a compromised
sub-agent should not be able to spin up unrelated infrastructure.
"""

from decepticon.tools.ops.tools import OPS_TOOLS, ops_start, ops_status, ops_stop

__all__ = ["OPS_TOOLS", "ops_start", "ops_status", "ops_stop"]
