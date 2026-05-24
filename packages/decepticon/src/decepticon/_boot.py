"""Framework boot — runs once at ``import decepticon`` time.

Hooks into the framework's import to:

  1. Register the 16 OSS roles with ``RoleRegistry`` so plugins can
     introspect and ``LLMFactory`` can consume the pluggable role
     catalog (gap §8 #5).
  2. Build the ``PluginRegistry`` singleton (entry-point walk +
     collision detection).
  3. Compose a ``RoleResolution`` per OSS role from the framework's
     local slot/skill knowledge and push it into ``PluginRegistry``
     so ``introspect_role()`` returns audit-grade snapshots
     (gap §8 #7).

This module is private (``_boot``); the framework re-imports it from
``decepticon/__init__.py``. Plugin authors interact with the
registries through their public API only.
"""

from __future__ import annotations

import logging

from decepticon_core.contracts.slots import SLOTS_PER_ROLE, MiddlewareSlot
from decepticon_core.plugin_loader import load_plugin_role_specs
from decepticon_core.registry import (
    MiddlewareInfo,
    PluginRegistry,
    RoleRegistry,
    RoleResolution,
)

logger = logging.getLogger(__name__)


def _oss_skill_sources_for(role: str) -> tuple[str, ...]:
    """Return the OSS default ``/skills/`` source paths for ``role``.

    Mirrors the framework's ``skills_sources_for`` (in
    ``decepticon.agents.middleware_slots``) for the baseline portion
    — plugin-contributed paths layer on top at agent-build time. We
    duplicate the baseline here so ``RoleRegistry`` carries the
    audit-time view that matches what the runtime actually loads
    (closes spec §8 gap #2).
    """
    return (f"/skills/standard/{role}/", "/skills/shared/")


def _register_oss_roles() -> None:
    """Pre-register the 16 OSS roles with ``RoleRegistry``.

    Idempotent — re-imports across multi-process workers all succeed
    silently (spec §16.4 #3). Each role is registered with its baseline
    ``skill_sources`` so ``RoleRegistry`` matches the runtime view;
    plugin-contributed paths layer on top at agent-build time
    (closes gap §8 #2).
    """
    for role, slots in SLOTS_PER_ROLE.items():
        RoleRegistry.register(
            role,
            slots=slots,
            skill_sources=_oss_skill_sources_for(role),
        )


def _register_plugin_roles() -> None:
    """Walk ``decepticon.roles`` entry-points and register each spec.

    Closes spec §8 gap #5 — plugins shipping ``RoleSpec`` under the
    new ``decepticon.roles`` entry-point group are first-class citizens
    of the framework's role catalog. ``RoleRegistry.register`` is
    idempotent on identical params and raises on conflicting params
    (per spec §16.4 #3 strict semantics) — plugin authors who need
    replace semantics call ``unregister`` first.
    """
    for spec in load_plugin_role_specs():
        try:
            RoleRegistry.register(
                spec.name,
                slots=spec.slots,
                skill_sources=getattr(spec, "skill_sources", ()),
                llm_role_fallback=getattr(spec, "llm_role_fallback", None),
            )
        except ValueError:
            logger.exception(
                "plugin role registration failed for %r — already registered "
                "with different parameters",
                getattr(spec, "name", "<unknown>"),
            )


def _push_role_resolutions() -> None:
    """Compose a ``RoleResolution`` per OSS role + register with
    ``PluginRegistry``.

    Closes spec §8 gap #7 — audit consumers call
    ``PluginRegistry.load().introspect_role(role)`` and receive a
    deterministic, hashable snapshot suitable as a SOC2/HIPAA evidence
    primitive (spec §16.2).

    Fields populated:
      * ``middleware_stack`` — every slot in ``SLOTS_PER_ROLE[role]``,
        attributed to ``decepticon`` as owner (plugin overrides change
        attribution; not modelled here yet).
      * ``skill_sources`` — the OSS baseline paths (mirrors
        ``RoleRegistry``). Plugin contributions append at runtime via
        ``load_plugin_skill_sources``; that delta is not snapshot here
        because it varies per invocation, but the baseline is the
        contract layer's view.
      * ``tool_list`` — left empty because the OSS tool catalog per
        role is computed inside ``build_tools(role)`` (langchain-
        bound, framework-side) and varies with plugin contributions.
        Audit consumers that need this query the role-specific factory
        directly.
      * ``llm_model`` — empty: the assignment is per-invocation
        (``LLMFactory.get_model(role)`` resolves against env credentials
        at the time of the call). Snapshot would be misleading.
      * ``overrides_applied`` — empty for pure-OSS; populated when
        plugin-shipped ``PluginBundle`` overrides are tracked through
        ``_resolve_overrides``.
    """
    from decepticon.agents.middleware_slots import skills_sources_for as _osss

    for role, slots in SLOTS_PER_ROLE.items():
        middleware_stack = tuple(
            MiddlewareInfo(slot=slot.value, name=slot.value, owner="decepticon")
            for slot in MiddlewareSlot
            if slot in slots
        )
        # Use the framework's authoritative skills_sources_for so the
        # snapshot includes plugin-contributed paths discovered through
        # the ``decepticon.skills`` entry-point group at boot time.
        # ``load_plugin_skill_sources`` already swallows per-plugin
        # errors internally, so any exception escaping here indicates
        # a framework bug worth failing the boot.
        skill_sources = tuple(_osss(role))
        resolution = RoleResolution(
            role=role,
            middleware_stack=middleware_stack,
            tool_list=(),
            skill_sources=skill_sources,
            llm_model="",
            overrides_applied=(),
        )
        PluginRegistry.set_role_resolution(role, resolution)


def run() -> None:
    """Execute framework boot — idempotent."""
    _register_oss_roles()
    _register_plugin_roles()
    PluginRegistry.load()
    _push_role_resolutions()
    logger.debug(
        "decepticon framework boot complete (%d OSS + N plugin roles registered, %d resolutions)",
        len(SLOTS_PER_ROLE),
        len(SLOTS_PER_ROLE),
    )


__all__ = ["run"]
