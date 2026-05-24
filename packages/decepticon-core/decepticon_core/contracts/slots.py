"""Middleware slot enum and per-role applicability mapping.

The Decepticon agent factories assemble their middleware stack by
walking ``MiddlewareSlot`` in declaration order; each role declares
which slots apply via ``SLOTS_PER_ROLE``.

This module is the pure-data half of the original
``decepticon.agents.middleware_slots``. The langchain/deepagents-bound
default factories (``DEFAULT_SLOT_FACTORIES`` and the ``_make_*``
helpers) stay in the framework — keeping core langchain-free.

Plugin authors implementing custom middleware reach for
``MiddlewareSlot`` and the ``SAFETY_CRITICAL_SLOTS`` set when wiring
``PluginBundle.replaced_middleware`` / ``disabled_middleware``.
"""

from __future__ import annotations

from enum import StrEnum


class MiddlewareSlot(StrEnum):
    """Named slots in the agent middleware stack.

    Enum declaration order = assembly order. The 16 agent factories
    walk this enum top-to-bottom; only slots in ``SLOTS_PER_ROLE[role]``
    are instantiated.
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
``decepticon.agents.build``. Plugins are expected to honour the
overall contract (e.g. a replacement EngagementContextMiddleware still
needs to inject scope) — the gate exists so an accidentally-installed
plugin can't silently subvert the safety story.
"""


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


__all__ = [
    "MiddlewareSlot",
    "SAFETY_CRITICAL_SLOTS",
    "SLOTS_PER_ROLE",
]
