"""Agent protocol — minimum compiled-agent surface.

Plugins shipping a custom main agent or sub-agent return an object
conforming to this Protocol from their factory function. The
``SubAgentSpec.factory`` field (in ``decepticon_core.plugin_loader``)
is typed against this Protocol so the framework can wire sub-agents
into ``SubAgentMiddleware`` without inspecting concrete classes.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentProtocol(Protocol):
    """Contract for a compiled Decepticon agent.

    Mandatory attribute:
        name: agent identifier (matches the role name in
        ``SLOTS_PER_ROLE`` for OSS-shipped agents).

    Mandatory method:
        ``invoke`` — entry point used by orchestrators and the
        ``SubAgentMiddleware``; accepts a state object, returns the
        updated state.
    """

    name: str

    def invoke(self, state: Any, *, config: Any | None = None) -> Any: ...
