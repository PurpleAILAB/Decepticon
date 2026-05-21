"""Agent build helpers — the bridge between the slot registry, the
plugin loader, and the per-agent factory functions.

Two override channels feed into the same pipeline:

  1. **Library callers** pass langchain-style kwargs directly to the
     factory (``create_soundwave_agent(tools=[...], middleware=[...],
     system_prompt="...")``) — when provided, each kwarg fully replaces
     the OSS baseline for that surface and the plugin overrides below
     are skipped for it. ``None`` (default) builds the baseline AND
     applies plugin overrides.

  2. **Plugin packages** ship declarative ``PluginBundle`` objects under
     the ``decepticon.bundles`` entry-point group. The bundle carries
     fine-grained shape (``replaced_middleware``, ``disabled_tools``,
     ``prompts``, ``replaced_subagents`` ...) and ``build_middleware`` /
     ``build_tools`` apply them when the corresponding factory kwarg is
     unset.

Conflict resolution: explicit factory kwargs win over plugin
entry-points. The rationale is library callers usually want to opt out
of a plugin's override for a specific agent without uninstalling it.

Safety: a small allowlist of slots and tools are flagged
``safety_critical``. Disabling or replacing them requires
``DECEPTICON_ALLOW_SAFETY_OVERRIDES=1`` in the environment; otherwise
``SafetyOverrideViolation`` is raised at agent-construction time.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any

from decepticon.agents.middleware_slots import (
    DEFAULT_SLOT_FACTORIES,
    SAFETY_CRITICAL_SLOTS,
    SLOTS_PER_ROLE,
    MiddlewareSlot,
)
from decepticon.plugin_loader import (
    PluginBundle,
    is_bundle_enabled,
    load_plugin_middleware,
    load_plugin_tools,
)

logger = logging.getLogger(__name__)

# Tools flagged safety-critical. Disabling or replacing requires the
# env gate — they are the operator-approval and engagement-handoff
# signals; silently replacing them is the difference between an agent
# that asks permission and one that doesn't.
SAFETY_CRITICAL_TOOLS: frozenset[str] = frozenset(
    {
        "ask_user_question",
        "complete_engagement_planning",
    }
)

# Environment variable that unlocks safety-critical overrides for the
# current process. Single-value (not per-component) on purpose — easier
# to audit, harder to mis-configure.
SAFETY_OVERRIDE_ENV: str = "DECEPTICON_ALLOW_SAFETY_OVERRIDES"

# Entry-point group for declarative ``PluginBundle`` overrides. The
# existing ``decepticon.tools`` / ``decepticon.middleware`` /
# ``decepticon.callbacks`` groups stay for additive contributions; this
# new group is exclusively for plugins that need to disable or replace
# pieces of the standard stack.
BUNDLES_GROUP: str = "decepticon.bundles"


# ─────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────


class SafetyOverrideViolation(RuntimeError):
    """Raised when a plugin or library caller tries to disable or replace
    a safety-critical slot/tool without the ``DECEPTICON_ALLOW_SAFETY_OVERRIDES``
    env gate set."""


# ─────────────────────────────────────────────────────────────────────
# Bundle discovery
# ─────────────────────────────────────────────────────────────────────


def _iter_override_bundles(role: str) -> Iterator[PluginBundle]:
    """Yield every ``PluginBundle`` registered under
    ``decepticon.bundles`` that is enabled AND scoped to ``role``."""
    try:
        eps = list(entry_points(group=BUNDLES_GROUP))
    except Exception:  # noqa: BLE001 — entry-point introspection is best-effort
        logger.exception("plugin discovery failed for group %s", BUNDLES_GROUP)
        return

    for ep in eps:
        try:
            obj = ep.load()
        except Exception:  # noqa: BLE001
            logger.exception("failed to load %s:%s", BUNDLES_GROUP, ep.name)
            continue
        # Accept either a PluginBundle instance or a zero-arg factory
        # returning one — mirrors the dual shape ``_discover`` already
        # accepts for the additive groups.
        if callable(obj) and not isinstance(obj, PluginBundle):
            try:
                obj = obj()
            except Exception:  # noqa: BLE001
                logger.exception("override bundle factory %s raised", ep.name)
                continue
        if not isinstance(obj, PluginBundle):
            logger.warning(
                "entry-point %s:%s did not return a PluginBundle (got %r); skipping",
                BUNDLES_GROUP,
                ep.name,
                type(obj).__name__,
            )
            continue
        if not is_bundle_enabled(obj.bundle):
            continue
        if not obj.matches_role(role):
            continue
        yield obj


# ─────────────────────────────────────────────────────────────────────
# Override resolution
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ResolvedOverrides:
    """Merge of plugin entry-point + explicit kwarg overrides for one role."""

    middleware_replace: dict[str, Callable[..., Any]] = field(default_factory=dict)
    middleware_disable: frozenset[str] = field(default_factory=frozenset)
    tool_replace: dict[str, Any] = field(default_factory=dict)
    tool_disable: frozenset[str] = field(default_factory=frozenset)
    prompt: dict[str, str] = field(default_factory=dict)


def _resolve_overrides(
    *,
    role: str,
    explicit_middleware_replace: dict[MiddlewareSlot, Callable[..., Any]] | None,
    explicit_middleware_disable: set[MiddlewareSlot] | None,
    explicit_tool_replace: dict[str, Any] | None,
    explicit_tool_disable: set[str] | None,
    explicit_prompt: dict[str, str] | None,
) -> _ResolvedOverrides:
    """Walk plugin bundles + merge with explicit kwargs.

    Explicit wins on conflict. Plugin bundles for the same component
    likewise resolve via last-write-wins (we don't try to detect plugin
    A vs plugin B conflict — that's a future enhancement).
    """
    mw_replace: dict[str, Callable[..., Any]] = {}
    mw_disable: set[str] = set()
    tool_replace: dict[str, Any] = {}
    tool_disable: set[str] = set()
    prompt: dict[str, str] = {}

    for bundle in _iter_override_bundles(role):
        mw_replace.update(bundle.replaced_middleware)
        mw_disable.update(bundle.disabled_middleware)
        tool_replace.update(bundle.replaced_tools)
        tool_disable.update(bundle.disabled_tools)
        bundle_prompt = bundle.prompts.get(role) or {}
        for k in ("prepend", "append", "replace"):
            if k in bundle_prompt:
                prompt[k] = bundle_prompt[k]

    # Explicit kwargs override plugin entry-points
    if explicit_middleware_replace:
        for slot, factory in explicit_middleware_replace.items():
            mw_replace[slot.value] = factory
    if explicit_middleware_disable:
        mw_disable.update(s.value for s in explicit_middleware_disable)
    if explicit_tool_replace:
        tool_replace.update(explicit_tool_replace)
    if explicit_tool_disable:
        tool_disable.update(explicit_tool_disable)
    if explicit_prompt:
        prompt.update(explicit_prompt)

    return _ResolvedOverrides(
        middleware_replace=mw_replace,
        middleware_disable=frozenset(mw_disable),
        tool_replace=tool_replace,
        tool_disable=frozenset(tool_disable),
        prompt=prompt,
    )


def _check_safety_gate(
    *,
    role: str,
    mw_replace: dict[str, Callable[..., Any]],
    mw_disable: frozenset[str],
    tool_replace: dict[str, Any],
    tool_disable: frozenset[str],
) -> None:
    """Raise ``SafetyOverrideViolation`` when a safety-critical
    slot/tool is being overridden without the env gate."""
    if os.environ.get(SAFETY_OVERRIDE_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return

    safety_slots = {s.value for s in SAFETY_CRITICAL_SLOTS}
    mw_breach = (set(mw_replace.keys()) | mw_disable) & safety_slots
    tool_breach = (set(tool_replace.keys()) | tool_disable) & SAFETY_CRITICAL_TOOLS

    if not mw_breach and not tool_breach:
        return

    bits = []
    if mw_breach:
        bits.append(f"middleware slots {sorted(mw_breach)}")
    if tool_breach:
        bits.append(f"tools {sorted(tool_breach)}")
    raise SafetyOverrideViolation(
        f"Plugin or library caller for role={role!r} tried to override "
        f"safety-critical {' and '.join(bits)}. Set "
        f"{SAFETY_OVERRIDE_ENV}=1 in the environment to allow this. "
        f"Doing so disables a guard rail — only flip it when the "
        f"replacement honours the same contract (e.g. a replacement "
        f"EngagementContextMiddleware still injects RoE scope)."
    )


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def build_middleware(
    *,
    role: str,
    backend: Any,
    llm: Any,
    fallback_models: list | None = None,
    sandbox: Any = None,
    subagents: list | None = None,
    skill_sources: list[str] | None = None,
    overrides: dict[MiddlewareSlot, Callable[..., Any]] | None = None,
    disabled_slots: set[MiddlewareSlot] | None = None,
    slots: frozenset[MiddlewareSlot] | None = None,
) -> list:
    """Build the middleware stack for ``role``.

    Args:
        role: agent role name. Used for plugin-override scoping (via
            ``PluginBundle.roles``) and passed to every slot factory.
        backend: deepagents-style filesystem backend (the result of
            ``make_agent_backend`` — usually ``CompositeBackend``).
        llm: bound language model for summarization + per-slot use.
        fallback_models: list passed to ``ModelFallbackMiddleware``;
            empty / None skips the MODEL_FALLBACK slot.
        sandbox: the underlying ``HTTPSandbox`` instance — required for
            the SANDBOX_NOTIFICATION slot if the role uses it.
        subagents: list of ``CompiledSubAgent`` instances for the
            SUBAGENT slot (orchestrators only).
        skill_sources: explicit ``/skills/<bundle>/`` paths for the
            SKILLS slot. ``None`` (default) falls back to the OSS
            convention in ``skills_sources_for(role)`` for the 10
            standard roles. Plugin-shipped specialists and commercial
            agents pass an explicit list — the previous hardcoded
            ``_PLUGIN_SPECIALIST_ROLES`` registry is gone.
        overrides: explicit slot-replacement mapping. Wins over plugin
            entry-point bundles on conflict.
        disabled_slots: explicit slots to skip.
        slots: middleware slots this agent uses, in canonical enum order.
            ``None`` (default) looks the role up in ``SLOTS_PER_ROLE`` —
            the 16 OSS roles ship with mappings there. **Plugin-shipped
            orchestrators with a custom role name MUST pass an explicit
            ``slots`` set** since ``SLOTS_PER_ROLE`` only knows OSS
            roles; without this, the assembler refuses rather than
            silently building an empty stack.

    Returns:
        ordered list of middleware instances, ready to pass to
        ``create_agent(..., middleware=...)``.
    """
    if slots is None:
        slots = SLOTS_PER_ROLE.get(role)
    if slots is None:
        raise KeyError(
            f"unknown role {role!r}; pass ``slots=`` explicitly "
            f"(plugin orchestrators with a custom role) or add the role "
            f"to SLOTS_PER_ROLE in decepticon/agents/middleware_slots.py "
            f"(OSS roles)."
        )
    role_slots = slots

    resolved = _resolve_overrides(
        role=role,
        explicit_middleware_replace=overrides,
        explicit_middleware_disable=disabled_slots,
        explicit_tool_replace=None,
        explicit_tool_disable=None,
        explicit_prompt=None,
    )
    _check_safety_gate(
        role=role,
        mw_replace=resolved.middleware_replace,
        mw_disable=resolved.middleware_disable,
        tool_replace={},
        tool_disable=frozenset(),
    )

    factories: dict[str, Callable[..., Any]] = {
        slot.value: factory for slot, factory in DEFAULT_SLOT_FACTORIES.items()
    }
    factories.update(resolved.middleware_replace)

    result: list = []
    for slot in MiddlewareSlot:  # canonical enum order
        if slot not in role_slots:
            continue
        if slot.value in resolved.middleware_disable:
            continue
        instance = factories[slot.value](
            backend=backend,
            llm=llm,
            role=role,
            fallback_models=fallback_models,
            sandbox=sandbox,
            subagents=subagents,
            skill_sources=skill_sources,
        )
        # Some slot factories return None when their precondition isn't
        # met (e.g. MODEL_FALLBACK with empty fallback_models). Skip.
        if instance is None:
            continue
        result.append(instance)

    # Additive plugin middleware appended after the standard slots —
    # backward-compat escape hatch for plugins that just want to TACK
    # a middleware on the end without replacing anything.
    result.extend(load_plugin_middleware(role=role, backend=backend))

    return result


def build_tools(
    *,
    role: str,
    standard_tools: dict[str, Any] | list[Any] | None = None,
    overrides: dict[str, Any] | None = None,
    disabled_tools: set[str] | None = None,
) -> list[Any]:
    """Build the tools list for ``role``.

    Args:
        role: agent role name (for plugin scope + tool-registry lookup).
        standard_tools: the agent's baseline tools — either a
            ``dict[name, tool]`` (preferred — direct override by name)
            or a plain ``list[tool]`` (we infer names via ``.name``
            attribute).
        overrides: name → replacement tool. Wins over plugin overrides.
        disabled_tools: tool names to drop from the baseline.

    Returns:
        list of tools ready for ``create_agent(..., tools=...)``.
    """
    # Normalize the baseline into a name-keyed dict
    if standard_tools is None:
        base: dict[str, Any] = {}
    elif isinstance(standard_tools, dict):
        base = dict(standard_tools)
    else:
        base = {_tool_name(t): t for t in standard_tools}

    resolved = _resolve_overrides(
        role=role,
        explicit_middleware_replace=None,
        explicit_middleware_disable=None,
        explicit_tool_replace=overrides,
        explicit_tool_disable=disabled_tools,
        explicit_prompt=None,
    )
    _check_safety_gate(
        role=role,
        mw_replace={},
        mw_disable=frozenset(),
        tool_replace=resolved.tool_replace,
        tool_disable=resolved.tool_disable,
    )

    for name in resolved.tool_disable:
        base.pop(name, None)
    base.update(resolved.tool_replace)

    result = list(base.values())
    result.extend(load_plugin_tools(role=role))
    return result


def _tool_name(tool: Any) -> str:
    """Best-effort tool name extraction for list-shaped baselines.

    ``langchain_core`` ``@tool`` decorated callables expose ``.name``;
    plain callables fall back to ``__name__``. We need this to keep the
    list-shape baseline backwards compatible with the dict shape used
    by override logic.
    """
    if hasattr(tool, "name") and isinstance(tool.name, str):
        return tool.name
    return getattr(tool, "__name__", repr(tool))


def resolve_prompt_overrides(
    role: str,
    *,
    override: str | dict[str, str] | None = None,
) -> dict[str, str]:
    """Return the prompt-shaping dict for ``role`` (prepend/append/replace).

    Used by ``load_prompt`` in ``decepticon.agents.prompts`` — kept
    here so plugin / safety-gate logic lives next to the rest of the
    override machinery. Callers do NOT include ``decepticon.agents.prompts``
    here; that module imports this function and applies the dict to the
    loaded base prompt.

    Args:
        role: agent role name.
        override: explicit prompt override from the library caller.
            ``str`` = full replace. ``dict`` = prepend/append/replace
            keyed entries. ``None`` = only plugin overrides apply.

    Returns:
        dict with at most three keys: ``prepend``, ``append``, ``replace``.
        Caller applies ``replace`` first (if present), then
        ``prepend`` + ``append`` to the base / replaced prompt.
    """
    explicit_dict: dict[str, str] = {}
    if isinstance(override, str):
        explicit_dict["replace"] = override
    elif isinstance(override, dict):
        for k in ("prepend", "append", "replace"):
            if k in override:
                explicit_dict[k] = override[k]

    resolved = _resolve_overrides(
        role=role,
        explicit_middleware_replace=None,
        explicit_middleware_disable=None,
        explicit_tool_replace=None,
        explicit_tool_disable=None,
        explicit_prompt=explicit_dict,
    )
    return dict(resolved.prompt)
