"""Middleware protocol — matches the langchain agent middleware shape.

Plugin authors implementing custom middleware conform to this Protocol
and register via the ``decepticon.middleware`` entry-point group (or
ship a ``PluginBundle`` that replaces a standard slot). The framework
walks ``MiddlewareSlot`` in canonical order; middleware classes are
called at agent invocation time.

See spec §7.2 Principle 1 for the design rationale (one Protocol per
extension type so plugin authors read exactly one document to ship).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from decepticon_core.contracts.slots import MiddlewareSlot


@runtime_checkable
class MiddlewareProtocol(Protocol):
    """Contract for plugin-contributed middleware.

    Mandatory attributes:
        name: human-readable middleware identifier (for introspection)
        slot: which ``MiddlewareSlot`` this occupies — accepts the enum
            value or a custom string for plugin-introduced slots
        priority: assembly ordering hint inside the slot (lower wins).
            OSS-shipped middleware uses 100/200/...; plugins typically
            ship 50 (replace before) or 150 (replace after).

    Mandatory method:
        ``wrap_model_call`` — primary callback the agent runner invokes.

    Optional hooks (any subset, framework calls those present):
        ``before_agent``, ``after_agent``, ``modify_request``.
    """

    name: str
    slot: MiddlewareSlot | str
    priority: int

    def wrap_model_call(self, state: Any, runtime: Any, config: Any) -> Any: ...
