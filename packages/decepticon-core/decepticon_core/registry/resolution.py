"""Role resolution snapshot — returned by ``PluginRegistry.introspect_role()``.

Per spec §16.4 #1 the dataclass uses ``frozen=True`` with tuple-typed
collections so instances are hashable + cacheable. Audit systems
memoize ``RoleResolution`` per run-id to attribute middleware / tool
selection decisions deterministically (required for SOC2/HIPAA
evidence retention).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MiddlewareInfo:
    """Static description of a middleware in the resolved stack.

    Carries only fields useful for audit attribution; the runtime
    instance lives elsewhere (the framework builds it from the slot
    factory or the plugin's ``PluginBundle.replaced_middleware``).
    """

    slot: str
    name: str
    owner: str


@dataclass(frozen=True)
class ToolInfo:
    """Static description of a tool in the resolved tool list."""

    name: str
    owner: str


@dataclass(frozen=True)
class OverrideInfo:
    """Static description of one override applied at resolution time.

    Carries the surface kind (tool / middleware / prompt / subagent),
    the key, and the plugin owner. Used to populate the
    ``overrides_applied`` tuple in ``RoleResolution``.
    """

    kind: str
    key: str
    owner: str
    action: str


@dataclass(frozen=True)
class RoleResolution:
    """Read-only snapshot of one role's resolved configuration.

    Returned by ``PluginRegistry.introspect_role(role)``. All
    collections are tuples (not lists) so instances are hashable —
    audit pipelines memoize on ``(run_id, role)``.

    Read-only by contract (spec §16.4 #2): introspect is called from
    audit contexts and must never mutate registry state.
    """

    role: str
    middleware_stack: tuple[MiddlewareInfo, ...]
    tool_list: tuple[ToolInfo, ...]
    skill_sources: tuple[str, ...]
    llm_model: str
    overrides_applied: tuple[OverrideInfo, ...]
