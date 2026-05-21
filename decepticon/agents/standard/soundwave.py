"""Soundwave Agent — engagement document writer.

Generates the eight planning documents (RoE / CONOPS / Deconfliction /
Threat Profile / Contact / Data Handling / Abort / Cleanup) that frame
the red team engagement. Does NOT generate OPPLAN — the orchestrator
owns OPPLAN directly via OPPLANMiddleware.

Named after the Decepticon intelligence officer who intercepts, processes,
and organizes strategic information for Megatron's operations.

Library-style factory
---------------------
``create_soundwave_agent()`` accepts override kwargs (mirroring the
``deepagents.create_deep_agent`` / ``langchain.create_agent`` shape).
Library callers compose freely; Docker / plugin authors get the same
override semantics declaratively via ``PluginBundle`` entry-points
under ``decepticon.bundles``.

Standard middleware stack (12 slots, per role applicability — see
``decepticon.agents.middleware_slots.SLOTS_PER_ROLE``):

  ENGAGEMENT_CONTEXT → SKILLS → FILESYSTEM → MODEL_FALLBACK
    → SUMMARIZATION → PROMPT_CACHING → PATCH_TOOL_CALLS

No SubAgent / OPPLAN (soundwave is standalone, not an orchestrator).
No SandboxNotification (soundwave is document-only, no bash tool).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent

from decepticon.agents.assembly import assemble_middleware, assemble_tools
from decepticon.agents.middleware_slots import MiddlewareSlot
from decepticon.agents.prompts import load_prompt_with_overrides
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.plugin_loader import load_plugin_callbacks
from decepticon.tools.interaction import ask_user_question, complete_engagement_planning

# Standard tools, name-keyed so plugin overrides can target them.
# Library callers can pass ``tool_overrides={"ask_user_question": ...}`` to
# swap; declarative plugins put the same key in
# ``PluginBundle.replaced_tools``.
_STANDARD_TOOLS: dict[str, Any] = {
    "ask_user_question": ask_user_question,
    "complete_engagement_planning": complete_engagement_planning,
}

_ROLE = "soundwave"
_RECURSION_LIMIT = 200


def create_soundwave_agent(
    *,
    backend: Any = None,
    llm: Any = None,
    fallback_models: list | None = None,
    middleware_overrides: dict[MiddlewareSlot, Callable[..., Any]] | None = None,
    disabled_slots: set[MiddlewareSlot] | None = None,
    tool_overrides: dict[str, Any] | None = None,
    disabled_tools: set[str] | None = None,
    system_prompt: str | dict[str, str] | None = None,
    recursion_limit: int | None = None,
):
    """Build the Soundwave agent with optional library-style overrides.

    Args:
        backend: deepagents-style filesystem backend. Defaults to
            ``make_agent_backend(build_sandbox_backend())`` — the
            standard CompositeBackend over the HTTP sandbox transport.
        llm: bound chat model. Defaults to ``LLMFactory().get_model("soundwave")``.
        fallback_models: passed to ModelFallbackMiddleware. Defaults to
            ``LLMFactory().get_fallback_models("soundwave")``.
        middleware_overrides: per-slot factory replacement. Keys are
            ``MiddlewareSlot`` enum members; values are zero-or-kwarg
            callables matching ``DEFAULT_SLOT_FACTORIES`` shape.
        disabled_slots: middleware slots to skip entirely.
        tool_overrides: name → replacement tool. Wins over plugin
            entry-point overrides on conflict.
        disabled_tools: tool names to remove from the baseline.
        system_prompt:
            - ``None`` — load the standard prompt + apply plugin overrides.
            - ``str`` — substitute the prompt entirely.
            - ``dict[str, str]`` with ``prepend`` / ``append`` /
              ``replace`` keys — partial prompt patching.
        recursion_limit: override the per-role default (200).

    Safety: disabling or replacing safety-critical slots / tools (see
    ``SAFETY_CRITICAL_SLOTS`` / ``SAFETY_CRITICAL_TOOLS``) raises
    ``SafetyOverrideViolation`` unless ``DECEPTICON_ALLOW_SAFETY_OVERRIDES=1``
    is set in the environment.
    """
    if llm is None or fallback_models is None:
        factory = LLMFactory()
        if llm is None:
            llm = factory.get_model(_ROLE)
        if fallback_models is None:
            fallback_models = factory.get_fallback_models(_ROLE)

    if backend is None:
        sandbox = build_sandbox_backend()
        backend = make_agent_backend(sandbox)

    prompt = load_prompt_with_overrides(_ROLE, override=system_prompt)

    middleware = assemble_middleware(
        role=_ROLE,
        backend=backend,
        llm=llm,
        fallback_models=fallback_models,
        sandbox=None,  # soundwave doesn't use SandboxNotification
        subagents=None,  # standalone — no SubAgent slot
        overrides=middleware_overrides,
        disabled_slots=disabled_slots,
    )

    tools = assemble_tools(
        role=_ROLE,
        standard_tools=_STANDARD_TOOLS,
        overrides=tool_overrides,
        disabled_tools=disabled_tools,
    )

    return create_agent(
        llm,
        system_prompt=prompt,
        tools=tools,
        middleware=middleware,
        name=_ROLE,
    ).with_config(
        {
            "recursion_limit": recursion_limit or _RECURSION_LIMIT,
            "callbacks": load_plugin_callbacks(role=_ROLE, backend=backend),
        }
    )


# Module-level graph for LangGraph Platform (langgraph serve).
# Uses default args — equivalent to the legacy unparameterised factory.
graph = create_soundwave_agent()
