"""Tool protocol — matches the langchain ``@tool``-decorated callable shape.

Plugin authors ship tools either as langchain ``@tool`` callables or
as classes implementing this Protocol. The framework's tool registry
(``decepticon.agents.build.build_tools``) accepts both shapes; this
Protocol documents the minimum surface.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolProtocol(Protocol):
    """Contract for plugin-contributed tools.

    Mandatory attributes:
        name: tool name exposed to the LLM (matches langchain ``.name``)
        description: human-readable tool description, surfaced in the
            LLM tool schema

    Mandatory method:
        ``invoke`` — synchronous call entry. The framework adapter
        bridges to ``ainvoke`` when the agent runs async, so sync-only
        plugins are still composable.
    """

    name: str
    description: str

    def invoke(self, input: Any, *, config: Any | None = None) -> Any: ...
