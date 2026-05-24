"""Focused contribution dataclasses for plugin authors.

Per spec §7.2 Principle 3, the kitchen-sink ``PluginBundle`` of the
pre-redesign era splits into five focused contribution types — each
covers one extension surface so plugin authors construct just what
they need and the framework's introspection (``PluginRegistry``)
attributes overrides to specific contributions.

The aggregate ``PluginBundle`` (currently at
``decepticon_core.plugin_loader``) keeps a back-compat shape during
the transition; Phase 2 introduces the rebuilt version that aggregates
these contributions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ToolContribution:
    """Tools a plugin contributes to one or more roles.

    Mirrors the old ``PluginBundle.replaced_tools`` / ``disabled_tools``
    fields, but typed precisely and with the ``roles`` field
    intentionally required (no implicit "all roles" — closes gap §8
    #6). An empty ``roles`` tuple raises ``ValueError`` at construction.

    Fields:
        items: tools added to the role's tool list.
        disabled_names: tool names to remove from the OSS baseline.
        replaced: name -> replacement tool (combines disable + add).
        roles: roles this contribution applies to. ``()`` is rejected
            at construction time.
    """

    items: tuple[Any, ...] = ()
    disabled_names: tuple[str, ...] = ()
    replaced: Mapping[str, Any] = field(default_factory=dict)
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.roles:
            raise ValueError(
                "ToolContribution requires an explicit non-empty ``roles=`` tuple "
                "(closes spec §8 gap #6 — implicit all-roles is forbidden). "
                "Pass roles=('recon',) etc."
            )


@dataclass(frozen=True)
class MiddlewareContribution:
    """Middleware a plugin contributes to one or more roles.

    Same shape as ``ToolContribution`` but keyed by slot name (the
    ``MiddlewareSlot`` value). ``roles`` is required at construction.
    """

    items: tuple[Any, ...] = ()
    disabled_slots: tuple[str, ...] = ()
    replaced_slots: Mapping[str, Any] = field(default_factory=dict)
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.roles:
            raise ValueError(
                "MiddlewareContribution requires an explicit non-empty "
                "``roles=`` tuple (closes spec §8 gap #6). Pass roles=('recon',) etc."
            )


@dataclass(frozen=True)
class PromptContribution:
    """Prompt fragments a plugin contributes to one or more roles.

    Closes gap §8 #8 (prompt-only plugin no longer has to wrap in
    ``PluginBundle``) — packages can ship a ``PromptContribution``
    directly under the new ``decepticon.prompts`` entry-point group.

    Fields:
        fragments: role name -> text. The framework applies the
            fragment per the ``mode`` setting.
        mode: ``prepend`` / ``append`` / ``replace`` (replace wholly
            substitutes the loaded prompt; prepend/append wrap it).
        roles: roles this contribution applies to.
    """

    fragments: Mapping[str, str] = field(default_factory=dict)
    mode: Literal["prepend", "append", "replace"] = "append"
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.roles:
            raise ValueError(
                "PromptContribution requires an explicit non-empty ``roles=`` "
                "tuple (closes spec §8 gap #6). Pass roles=('recon',) etc."
            )


@dataclass(frozen=True)
class SubAgentContribution:
    """Sub-agents a plugin contributes to one or more parent agents.

    Mirrors the parent-agent scoping used by ``load_subagents_for_parent``
    in ``decepticon_core.plugin_loader``. The ``items`` carry
    ``SubAgentSpec`` objects (defined in plugin_loader, eventually to
    move under ``contracts``). ``parent_agents`` required.
    """

    items: tuple[Any, ...] = ()
    disabled_names: tuple[str, ...] = ()
    replaced: Mapping[str, Any] = field(default_factory=dict)
    parent_agents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.parent_agents:
            raise ValueError(
                "SubAgentContribution requires an explicit non-empty "
                "``parent_agents=`` tuple (closes spec §8 gap #6). "
                "Pass parent_agents=('decepticon',) etc."
            )


@dataclass(frozen=True)
class SafetyDeclaration:
    """Plugin-declared additions to the safety-critical set.

    Per spec §16.4 #4 this contract is **additive only**: plugins can
    declare *their own* tool / middleware names safety-critical, but
    cannot remove safety on OSS-declared names. The framework merges
    plugin SafetyDeclarations with ``SAFETY_CRITICAL_TOOLS`` /
    ``SAFETY_CRITICAL_SLOTS`` from ``decepticon-core``.

    Fields:
        tools: tool names the plugin marks safety-critical.
        middleware: middleware slot names the plugin marks
            safety-critical. Custom plugin slot names are accepted
            (any string).
    """

    tools: tuple[str, ...] = ()
    middleware: tuple[str, ...] = ()


__all__ = [
    "MiddlewareContribution",
    "PromptContribution",
    "SafetyDeclaration",
    "SubAgentContribution",
    "ToolContribution",
]
