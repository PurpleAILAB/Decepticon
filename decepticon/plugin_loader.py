"""Plugin discovery for Decepticon.

Decepticon supports adding tools, middleware, agents, and callback handlers
without modifying the OSS codebase. External packages declare their
contributions via Python entry-points; agent factories pick them up at
construction time.

Entry-point groups (declared by the consuming package's pyproject.toml):

    [project.entry-points."decepticon.tools"]
    my-tools = "my_pkg.tools:get_tools"

    [project.entry-points."decepticon.middleware"]
    my-mw = "my_pkg.middleware:get_middleware"

    [project.entry-points."decepticon.agents"]
    my-agent = "my_pkg.agents.my_agent"

    [project.entry-points."decepticon.callbacks"]
    my-cb = "my_pkg.callbacks:get_callbacks"

The exported object can be:
  - a ``list``/``tuple`` of items — returned as-is.
  - a callable factory accepting kwargs — called with ``role=<role>`` plus
    any dependency kwargs (e.g. ``backend``); its return value is treated
    as a list.
  - a single runtime instance (tool / middleware / callback) — wrapped in
    a one-element list.

A plugin that raises on load is logged and skipped; the agent factory
falls back to OSS-only behavior. This keeps OSS robust against plugin
bugs and absent plugin environments (pure OSS users see no behavior change).
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

TOOLS_GROUP = "decepticon.tools"
MIDDLEWARE_GROUP = "decepticon.middleware"
AGENTS_GROUP = "decepticon.agents"
SUBAGENTS_GROUP = "decepticon.subagents"
CALLBACKS_GROUP = "decepticon.callbacks"


# ─────────────────────────────────────────────────────────────────────────────
# Bundle activation — 4-tier hybrid hierarchy (Claude-Code/Django style).
#
# Highest to lowest precedence (first one that sets a value wins):
#
#   1. DECEPTICON_PLUGINS env var          ← runtime override (Docker, CI)
#   2. .decepticon.toml [plugins].enabled  ← per-checkout opt-in (CWD)
#   3. pyproject.toml [tool.decepticon.plugins].enabled  ← project default (CWD)
#   4. Hardcoded default: {"standard"}     ← lean OSS baseline
#
# Special value ``"*"`` in any tier → wildcard sentinel (all bundles).
#
# External plugin packages always load when pip-installed; their
# entry-point contributions can wrap output in ``PluginBundle`` to opt
# into the same allowlist (e.g. ``bundle="saas"`` requires that string
# in DECEPTICON_PLUGINS / config file).
# ─────────────────────────────────────────────────────────────────────────────

PLUGINS_ENV_VAR = "DECEPTICON_PLUGINS"
DEFAULT_BUNDLES: frozenset[str] = frozenset({"standard"})
_WILDCARD: frozenset[str] = frozenset()  # empty frozenset sentinel — "all"


def _normalize_bundles_value(value: Any) -> frozenset[str] | None:
    """Convert a config-file value to a bundles frozenset.

    Accepts ``"*"`` (wildcard sentinel), ``["*"]``, comma-separated string,
    or list/tuple of strings. Returns None if the shape is invalid so the
    caller can fall through to the next tier rather than silently
    accepting garbage.
    """
    if value == "*" or value == ["*"]:
        return _WILDCARD
    if isinstance(value, str):
        return frozenset(name.strip() for name in value.split(",") if name.strip())
    if isinstance(value, (list, tuple)):
        return frozenset(str(v).strip() for v in value if str(v).strip())
    return None


def _config_file_bundles() -> frozenset[str] | None:
    """Resolve bundles from config files in CWD. Returns None if neither set.

    Lookup order (first match wins):
      1. ``.decepticon.toml`` →  ``[plugins] enabled = [...]``
      2. ``pyproject.toml``   →  ``[tool.decepticon.plugins] enabled = [...]``

    Read errors are logged and treated as "not configured" so a broken
    config file never blocks the loader — the next tier provides a
    fallback.
    """
    cwd = Path.cwd()

    decepticon_toml = cwd / ".decepticon.toml"
    if decepticon_toml.is_file():
        try:
            data = tomllib.loads(decepticon_toml.read_text(encoding="utf-8"))
            value = data.get("plugins", {}).get("enabled")
            if value is not None:
                normalized = _normalize_bundles_value(value)
                if normalized is not None:
                    return normalized
        except Exception:
            logger.exception("failed to read %s", decepticon_toml)

    pyproject = cwd / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            value = data.get("tool", {}).get("decepticon", {}).get("plugins", {}).get("enabled")
            if value is not None:
                normalized = _normalize_bundles_value(value)
                if normalized is not None:
                    return normalized
        except Exception:
            logger.exception("failed to read %s", pyproject)

    return None


def _enabled_bundles() -> frozenset[str]:
    """Resolve active bundles via 4-tier hybrid hierarchy.

    See module-level comment for tier order. Read at call time so tests
    and multi-process workers see env / config changes without restarting.
    """
    # Tier 1: env var override
    raw = os.environ.get(PLUGINS_ENV_VAR, "").strip()
    if raw:
        if raw == "*":
            return _WILDCARD
        return frozenset(name.strip() for name in raw.split(",") if name.strip())

    # Tier 2-3: config files in CWD
    file_value = _config_file_bundles()
    if file_value is not None:
        return file_value

    # Tier 4: hardcoded default
    return DEFAULT_BUNDLES


def is_bundle_enabled(bundle: str | None) -> bool:
    """Return True if ``bundle`` is active under current DECEPTICON_PLUGINS.

    - Wildcard env (``DECEPTICON_PLUGINS=*``) → True for any bundle.
    - ``bundle is None`` → True. Specs without a declared bundle are
      treated as "always-load when installed" (the package-install
      already implies opt-in, matching Claude Code's MCP-server model).
    - Otherwise: True iff ``bundle`` is in the active allowlist.
    """
    enabled = _enabled_bundles()
    if not enabled:
        return True
    if bundle is None:
        return True
    return bundle in enabled


@dataclass(frozen=True)
class PluginBundle:
    """Optional wrapper for entry-point contributions to declare bundle membership.

    Plugin authors who want bundle-level activation control wrap their
    tools / middleware / callbacks in this. Plain list returns (the
    existing convention) keep working as ``bundle=None`` — always-load
    when installed, matching Claude Code's MCP-server semantics.

    Example::

        # my_plugin/tools.py
        from decepticon.plugin_loader import PluginBundle
        from langchain_core.tools import tool

        @tool
        def my_premium_tool(query: str) -> str:
            ...

        # pyproject.toml entry-point points at this constant:
        TOOLS = PluginBundle(items=(my_premium_tool,), bundle="premium")

        # Only loaded when DECEPTICON_PLUGINS includes "premium".
    """

    items: tuple[Any, ...] = ()
    bundle: str | None = None


@dataclass(frozen=True)
class SubAgentSpec:
    """Description of a subagent that can be attached to a main agent.

    Used by ``load_subagents_for_parent`` to discover subagents registered
    via the ``decepticon.subagents`` entry-point group. The main agent
    factory looks up the specs whose ``parent_agents`` includes its own
    name and constructs a ``CompiledSubAgent`` for each one (with
    ``runnable=StreamingRunnable(spec.factory(), spec.name)``).

    Fields:
        name: subagent identifier exposed to the LLM through ``task()``.
        description: text shown to the LLM in the ``task`` tool schema.
        factory: zero-arg callable returning the compiled subagent (e.g.
            ``decepticon.agents.standard.recon.create_recon_agent``). The
            factory is invoked lazily by the main agent at construction
            time.
        parent_agents: tuple of main-agent names this subagent should be
            attached to (e.g. ``("decepticon",)`` or
            ``("decepticon", "vulnresearch")``).
        bundle: optional grouping label for organizational/audit purposes
            (e.g. ``"standard"`` for OSS-standard subagents,
            ``"plugins"`` for plugin-shape subagents, or any plugin
            package name for third-party contributions).
        priority: ordering hint within the list returned to the parent —
            lower comes first. Default 100. Standard OSS subagents use
            small explicit values (10, 20, ...) so their order is
            preserved; plugin subagents typically fall back to 100 and
            are appended at the end alphabetically.
        skill_sources: optional tuple of ``/skills/<x>/`` paths the
            subagent expects to find inside the sandbox. Reserved for
            future skill-routing wiring; main agents currently ignore.
    """

    name: str
    description: str
    factory: Callable[[], Any]
    parent_agents: tuple[str, ...] = ()
    bundle: str | None = None
    priority: int = 100
    skill_sources: tuple[str, ...] = field(default_factory=tuple)


# Attributes that distinguish a Tool/Middleware/Callback INSTANCE from a
# factory callable. If any of these are present we treat the object as a
# runtime object and skip the "call it as a factory" branch.
_RUNTIME_ATTRS = (
    "invoke",
    "args_schema",
    "before_agent",
    "modify_request",
    "after_agent",
    "on_llm_start",
    "on_tool_start",
)


def _looks_like_runtime_object(obj: Any) -> bool:
    """Heuristic — separate a runtime instance from a factory callable."""
    return any(hasattr(obj, attr) for attr in _RUNTIME_ATTRS)


def _discover(group: str, role: str | None, **deps: Any) -> list[Any]:
    """Discover entry-point contributions for one group."""
    found: list[Any] = []
    try:
        eps = list(entry_points(group=group))
    except Exception:  # pragma: no cover — importlib quirks across versions
        logger.exception("plugin discovery failed for group %s", group)
        return found

    for ep in eps:
        try:
            obj = ep.load()
        except Exception:
            logger.exception("failed to load plugin %s from group %s", ep.name, group)
            continue

        try:
            if callable(obj) and not _looks_like_runtime_object(obj):
                result = obj(role=role, **deps)
            else:
                result = obj
        except Exception:
            logger.exception("failed to invoke plugin factory %s in group %s", ep.name, group)
            continue

        # ``PluginBundle`` wrapper — apply bundle filter then unpack items.
        if isinstance(result, PluginBundle):
            if not is_bundle_enabled(result.bundle):
                continue
            found.extend(result.items)
        elif isinstance(result, (list, tuple)):
            found.extend(result)
        elif result is not None:
            found.append(result)

    return found


def load_plugin_tools(role: str | None = None, **deps: Any) -> list[Any]:
    """Discover tools contributed by external packages.

    Args:
        role: the agent role requesting tools (e.g. ``"recon"``). Plugins
            may use this to scope which tools they contribute.
        **deps: dependency keyword args forwarded to factory plugins
            (commonly ``backend``).
    """
    return _discover(TOOLS_GROUP, role=role, **deps)


def load_plugin_middleware(role: str | None = None, **deps: Any) -> list[Any]:
    """Discover middleware contributed by external packages.

    Args:
        role: the agent role requesting middleware.
        **deps: typically includes ``backend`` so middleware that needs
            sandbox access can be constructed correctly.
    """
    return _discover(MIDDLEWARE_GROUP, role=role, **deps)


def load_plugin_callbacks(role: str | None = None, **deps: Any) -> list[Any]:
    """Discover LangChain callback handlers contributed by external packages."""
    return _discover(CALLBACKS_GROUP, role=role, **deps)


def _discover_subagent_specs() -> list[SubAgentSpec]:
    """Discover every ``SubAgentSpec`` exported under ``decepticon.subagents``."""
    found: list[SubAgentSpec] = []
    try:
        eps = list(entry_points(group=SUBAGENTS_GROUP))
    except Exception:  # pragma: no cover
        logger.exception("plugin discovery failed for group %s", SUBAGENTS_GROUP)
        return found

    for ep in eps:
        try:
            obj = ep.load()
        except Exception:
            logger.exception(
                "failed to load subagent plugin %s from group %s",
                ep.name,
                SUBAGENTS_GROUP,
            )
            continue

        if isinstance(obj, SubAgentSpec):
            found.append(obj)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                if isinstance(item, SubAgentSpec):
                    found.append(item)
                else:
                    logger.warning(
                        "subagent plugin %s exported non-SubAgentSpec item: %r",
                        ep.name,
                        item,
                    )
        elif callable(obj):
            # callable factory shape — invoke with no args and treat result
            # like the spec-or-list shapes above.
            try:
                result = obj()
            except Exception:
                logger.exception(
                    "failed to invoke subagent factory %s in group %s",
                    ep.name,
                    SUBAGENTS_GROUP,
                )
                continue
            if isinstance(result, SubAgentSpec):
                found.append(result)
            elif isinstance(result, (list, tuple)):
                found.extend(s for s in result if isinstance(s, SubAgentSpec))
            else:
                logger.warning(
                    "subagent plugin %s returned unexpected value: %r",
                    ep.name,
                    result,
                )
        else:
            logger.warning(
                "subagent plugin %s exported neither SubAgentSpec nor factory: %r",
                ep.name,
                obj,
            )

    return found


def load_subagents_for_parent(parent: str) -> list[SubAgentSpec]:
    """Discover subagents for ``parent`` whose ``bundle`` is active.

    Two filters apply:
      1. ``parent`` must be in the spec's ``parent_agents`` tuple.
      2. The spec's ``bundle`` must be active under ``DECEPTICON_PLUGINS``
         (see ``is_bundle_enabled``).

    Returned in stable order: ``(priority, name)``. Main-agent factories
    iterate this list to build their ``SubAgentMiddleware`` roster, so
    adding a new subagent (OSS-side or plugin-side) is a pure
    entry-point registration — no main-agent edits required.

    Default ``DECEPTICON_PLUGINS=standard`` returns only ``bundle="standard"``
    subagents. To activate the OSS ``plugins`` bundle (vulnresearch family),
    set ``DECEPTICON_PLUGINS=standard,plugins``. SaaS plugin packages set
    their own bundle (e.g. ``bundle="saas"``) and the SaaS Docker image
    activates it via ``ENV DECEPTICON_PLUGINS=standard,saas``.
    """
    matched = [
        s
        for s in _discover_subagent_specs()
        if parent in s.parent_agents and is_bundle_enabled(s.bundle)
    ]
    matched.sort(key=lambda s: (s.priority, s.name))
    return matched


def load_plugin_agents() -> dict[str, str]:
    """Discover agent graph entry-points.

    Returns a mapping of ``agent_name`` → ``module:graph`` paths suitable
    for LangGraph Platform's ``LANGSERVE_GRAPHS`` env or ``langgraph.json``.
    Plugin agent modules MUST expose a module-level ``graph`` attribute,
    matching how OSS agents are wired (``decepticon/agents/recon.py:graph``).
    """
    found: dict[str, str] = {}
    try:
        eps = list(entry_points(group=AGENTS_GROUP))
    except Exception:  # pragma: no cover
        logger.exception("plugin discovery failed for group %s", AGENTS_GROUP)
        return found

    for ep in eps:
        module = ep.value.split(":", 1)[0]
        found[ep.name] = f"{module}:graph"

    return found
