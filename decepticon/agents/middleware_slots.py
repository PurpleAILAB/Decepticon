"""Middleware slot registry — the plugin-override foundation.

Every Decepticon agent factory composes its middleware stack from a
fixed, canonically-ordered list of named slots. Plugins replace or
disable slots by name via ``PluginBundle.replaced_middleware`` /
``PluginBundle.disabled_middleware`` — no inline middleware construction
in agent factories, which previously locked SaaS extensions out of the
standard stack.

Slot order is the canonical assembly order. The 16 agent factories all
walk ``MiddlewareSlot`` in declaration order; any slot the agent's role
opts out of (per ``SLOTS_PER_ROLE``) is skipped silently. Plugin-added
middleware (``PluginBundle.items`` of middleware shape) still appends
*after* the standard slots — this is the additive escape hatch for new
middleware that doesn't fit an existing slot.

Adding a new slot is a three-step change: add the enum member, add a
default factory under ``DEFAULT_SLOT_FACTORIES``, and pin the
applicability set in ``SLOTS_PER_ROLE``. Adding a new role likewise
needs an entry in ``SLOTS_PER_ROLE``.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

# Middleware classes & factory helpers — imported at module level so
# slot factories don't pay per-call import cost. langchain + langgraph
# packages are listed as runtime deps; only ``benchmark_skill_sources``
# is decepticon-internal.
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents._benchmark_mode import benchmark_skill_sources
from decepticon.middleware import (
    EngagementContextMiddleware,
    FilesystemMiddleware,
    OPPLANMiddleware,
    SkillsMiddleware,
)
from decepticon.middleware.model_override import ModelOverrideMiddleware
from decepticon.middleware.notifications import SandboxNotificationMiddleware
from decepticon.plugin_loader import load_plugin_skill_sources

# ─────────────────────────────────────────────────────────────────────
# Slot enum
# ─────────────────────────────────────────────────────────────────────


class MiddlewareSlot(StrEnum):
    """Named slots in the agent middleware stack.

    Enum declaration order = assembly order. The 16 agent factories walk
    this enum top-to-bottom; only slots in ``SLOTS_PER_ROLE[role]`` are
    instantiated.
    """

    ENGAGEMENT_CONTEXT = "engagement-context"
    SKILLS = "skills"
    FILESYSTEM = "filesystem"
    SUBAGENT = "subagent"
    OPPLAN = "opplan"
    SANDBOX_NOTIFICATION = "sandbox-notification"
    MODEL_OVERRIDE = "model-override"
    MODEL_FALLBACK = "model-fallback"
    SUMMARIZATION = "summarization"
    PROMPT_CACHING = "prompt-caching"
    PATCH_TOOL_CALLS = "patch-tool-calls"


# ─────────────────────────────────────────────────────────────────────
# Safety annotations
# ─────────────────────────────────────────────────────────────────────


SAFETY_CRITICAL_SLOTS: frozenset[MiddlewareSlot] = frozenset(
    {
        # EngagementContextMiddleware carries RoE constraints into every
        # tool call — disabling it lets an agent target out-of-scope
        # hosts without any guard rail. Replacement is fine if the new
        # middleware honours the same contract; full disable is the
        # actual hazard.
        MiddlewareSlot.ENGAGEMENT_CONTEXT,
        # SandboxNotification tracks background-job completion + emits
        # the CLI's ``● Background command`` event. Disabling it leaves
        # operator visibility broken on every background tool call.
        MiddlewareSlot.SANDBOX_NOTIFICATION,
    }
)
"""Slots a plugin can only replace/disable when
``DECEPTICON_ALLOW_SAFETY_OVERRIDES=1`` is set in the environment.

The gate is enforced by ``build_middleware`` in
``decepticon/agents/build.py``. Plugins are expected to honour the
overall contract (e.g. a replacement EngagementContextMiddleware still
needs to inject scope) — the gate exists so an accidentally-installed
plugin can't silently subvert the safety story.
"""


# ─────────────────────────────────────────────────────────────────────
# Per-role applicability
# ─────────────────────────────────────────────────────────────────────


# Common slots every agent uses (the "tail" of the middleware stack).
_TAIL_SLOTS: frozenset[MiddlewareSlot] = frozenset(
    {
        MiddlewareSlot.MODEL_FALLBACK,
        MiddlewareSlot.SUMMARIZATION,
        MiddlewareSlot.PROMPT_CACHING,
        MiddlewareSlot.PATCH_TOOL_CALLS,
    }
)

# Base slots — knowledge + filesystem + tail. Every agent gets these.
_BASE_SLOTS: frozenset[MiddlewareSlot] = _TAIL_SLOTS | {
    MiddlewareSlot.SKILLS,
    MiddlewareSlot.FILESYSTEM,
}

# Standard bash-executing agents (recon/exploit/postexploit/analyst/
# reverser/contract_auditor/cloud_hunter/ad_operator + plugin
# specialists verifier/patcher/scanner/exploiter): base + engagement
# context + sandbox notification.
_BASH_AGENT_SLOTS: frozenset[MiddlewareSlot] = _BASE_SLOTS | {
    MiddlewareSlot.ENGAGEMENT_CONTEXT,
    MiddlewareSlot.SANDBOX_NOTIFICATION,
}


SLOTS_PER_ROLE: dict[str, frozenset[MiddlewareSlot]] = {
    # ── Standard orchestrator ──
    "decepticon": _BASE_SLOTS
    | {
        MiddlewareSlot.ENGAGEMENT_CONTEXT,
        MiddlewareSlot.SUBAGENT,
        MiddlewareSlot.OPPLAN,
        MiddlewareSlot.MODEL_OVERRIDE,
    },
    # ── Standard non-bash agent (planning + interview) ──
    "soundwave": _BASE_SLOTS | {MiddlewareSlot.ENGAGEMENT_CONTEXT},
    # ── Standard bash-executing specialists ──
    "recon": _BASH_AGENT_SLOTS,
    "exploit": _BASH_AGENT_SLOTS,
    "postexploit": _BASH_AGENT_SLOTS,
    "analyst": _BASH_AGENT_SLOTS,
    "reverser": _BASH_AGENT_SLOTS,
    "contract_auditor": _BASH_AGENT_SLOTS,
    "cloud_hunter": _BASH_AGENT_SLOTS,
    "ad_operator": _BASH_AGENT_SLOTS,
    # ── Plugin orchestrator (no EngagementContext per the existing
    # vulnresearch factory — it consumes its parent's context) ──
    "vulnresearch": _BASE_SLOTS | {MiddlewareSlot.SUBAGENT, MiddlewareSlot.OPPLAN},
    # ── Plugin read-only specialist (no bash, no SandboxNotification) ──
    "detector": _BASE_SLOTS,
    # ── Plugin bash-executing specialists ──
    "verifier": _BASH_AGENT_SLOTS,
    "patcher": _BASH_AGENT_SLOTS,
    "scanner": _BASH_AGENT_SLOTS,
    "exploiter": _BASH_AGENT_SLOTS,
}
"""Role → slot-set mapping. The assembler only walks slots present in
the role's set; anything else is skipped silently. Plugin agents
register their own role here via the ``decepticon.agents`` entry-point
group (handled by ``plugin_loader``)."""


# ─────────────────────────────────────────────────────────────────────
# Skills sources — role-specific
# ─────────────────────────────────────────────────────────────────────


def skills_sources_for(role: str) -> list[str]:
    """Default SkillsMiddleware ``sources`` list for an OSS role.

    Returns the path list for one of the 10 standard OSS agents
    (``recon``, ``exploit``, ``soundwave``, ...). ``benchmark_skill_sources()``
    is appended when ``BENCHMARK_MODE`` is active — see
    ``decepticon/agents/_benchmark_mode.py``. Plugin-contributed paths
    (registered under the ``decepticon.skills`` entry-point group) are
    appended last so commercial / 3rd-party skills can layer on top of
    the OSS baseline without overriding the whole SKILLS slot factory.

    Plugin specialists (detector, scanner, vulnresearch, …) and any
    out-of-tree commercial agent should NOT rely on this fallback —
    they pass an explicit ``skill_sources=`` kwarg to ``build_middleware``
    instead (see the 6 OSS plugin factories for the canonical pattern).
    The fallback exists purely so the OSS 10 standard factories don't
    have to repeat ``[f"/skills/standard/{_ROLE}/", "/skills/shared/"]``
    each.
    """
    base = [f"/skills/standard/{role}/", "/skills/shared/", *benchmark_skill_sources()]
    return [*base, *load_plugin_skill_sources(role)]


# ─────────────────────────────────────────────────────────────────────
# Default slot factories
# ─────────────────────────────────────────────────────────────────────
#
# Each factory takes a uniform kwarg set: backend, llm, role,
# fallback_models, sandbox, subagents. Slots that don't need a
# particular kwarg ignore it (``**_`` keyword sink). The uniform
# signature lets ``build_middleware`` call every slot factory the
# same way — and lets plugin-supplied replacement factories drop in
# without surprising arg-shape mismatches.


def _make_engagement_context(**_: Any):
    return EngagementContextMiddleware()


def _make_skills(*, backend: Any, role: str, skill_sources: list[str] | None = None, **_: Any):
    sources = list(skill_sources) if skill_sources is not None else skills_sources_for(role)
    return SkillsMiddleware(backend=backend, sources=sources)


def _make_filesystem(*, backend: Any, **_: Any):
    return FilesystemMiddleware(backend=backend)


def _make_subagent(*, backend: Any, subagents: list | None = None, **_: Any):
    return SubAgentMiddleware(backend=backend, subagents=subagents or [])


def _make_opplan(*, backend: Any, **_: Any):
    return OPPLANMiddleware(backend=backend)


def _make_sandbox_notification(*, sandbox: Any = None, **_: Any):
    if sandbox is None:
        raise ValueError(
            "SandboxNotificationMiddleware requires a sandbox kwarg; "
            "the agent factory must pass the HTTPSandbox instance it built."
        )
    return SandboxNotificationMiddleware(sandbox=sandbox)


def _make_model_override(**_: Any):
    return ModelOverrideMiddleware()


def _make_model_fallback(*, fallback_models: list | None = None, **_: Any):
    """Conditional slot — returns None when no fallback chain exists.

    ``build_middleware`` filters None results out so the absent
    fallback simply skips the slot, mirroring the legacy
    ``if fallback_models: middleware.append(...)`` branch.
    """
    if not fallback_models:
        return None
    return ModelFallbackMiddleware(*fallback_models)


def _make_summarization(*, backend: Any, llm: Any, **_: Any):
    return create_summarization_middleware(llm, backend)


def _make_prompt_caching(**_: Any):
    return AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore")


def _make_patch_tool_calls(**_: Any):
    return PatchToolCallsMiddleware()


SlotFactory = Callable[..., Any]


DEFAULT_SLOT_FACTORIES: dict[MiddlewareSlot, SlotFactory] = {
    MiddlewareSlot.ENGAGEMENT_CONTEXT: _make_engagement_context,
    MiddlewareSlot.SKILLS: _make_skills,
    MiddlewareSlot.FILESYSTEM: _make_filesystem,
    MiddlewareSlot.SUBAGENT: _make_subagent,
    MiddlewareSlot.OPPLAN: _make_opplan,
    MiddlewareSlot.SANDBOX_NOTIFICATION: _make_sandbox_notification,
    MiddlewareSlot.MODEL_OVERRIDE: _make_model_override,
    MiddlewareSlot.MODEL_FALLBACK: _make_model_fallback,
    MiddlewareSlot.SUMMARIZATION: _make_summarization,
    MiddlewareSlot.PROMPT_CACHING: _make_prompt_caching,
    MiddlewareSlot.PATCH_TOOL_CALLS: _make_patch_tool_calls,
}
"""Slot → factory mapping. Plugin overrides shallow-merge into this
dict at assembly time (without mutating the module-level constant) —
see ``decepticon.agents.build.build_middleware``."""
