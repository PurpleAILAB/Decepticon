"""Blue Cell Agent — the defensive sibling that closes the Offensive Vaccine loop.

Red Cell attacks; the Detector writes Sigma rules. Blue Cell is the runtime
that proves those rules actually fire: it replays the engagement's own
activity through ``blue_cell_scan`` (tap + rule matcher), records each hit as a
``DetectionFired`` node in the knowledge graph — linked ``-[:USES_RULE]->`` the
rule and ``-[:DETECTED]->`` the Finding/Technique it caught — and reports the
**detection gaps** (Findings nothing detected) as the headline blue-team
deliverable. See ``docs/features/blue-cell.md``.

Key design choices — enforced by the tool surface, not just the prompt:

- **Read-only at runtime.** No ``bash`` tool, no ``SandboxNotification`` slot
  (``SLOTS_PER_ROLE["blue_cell"]`` maps to ``_BASE_SLOTS``, like ``detector``).
  Blue Cell observes the engagement; it never attacks.
- **No ``kg_add_node`` / ``kg_add_edge``.** Detections are recorded
  deterministically by ``blue_cell_scan`` (the matcher decides what fired) —
  the agent cannot fabricate detection coverage. It gets the read-only KG
  query subset to inspect Findings and narrate the gap report.

Library API
-----------
Factory shape mirrors ``langchain.agents.create_agent`` /
``deepagents.create_deep_agent`` — every keyword is optional, and explicit
values fully replace the OSS baseline:

  - ``tools=[...]``         full tool list (overrides the standard set)
  - ``middleware=[...]``    full middleware list (overrides the slot stack)
  - ``system_prompt="..."`` full prompt (overrides the loaded baseline)

When a keyword is ``None`` (default), the factory builds the OSS baseline AND
applies any plugin overrides discovered via the ``decepticon.bundles``
entry-point group.

No SandboxNotification (no bash tool). No SubAgent / OPPLAN (specialist).
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from decepticon.agents.build import build_middleware, build_tools
from decepticon.agents.prompts import load_prompt
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.tools.defense.blue_cell import blue_cell_scan
from decepticon.tools.defense.brief import defense_brief, export_attack_navigator
from decepticon.tools.research.tools import kg_neighbors, kg_query, kg_stats
from decepticon_core.plugin_loader import SubAgentSpec, is_bundle_enabled, load_plugin_callbacks

# Name-keyed baseline tools. Read-only by construction: the detection-coverage
# scanner + Defense Brief deliverables plus the KG query subset — no bash, no
# kg_add_node/kg_add_edge.
_STANDARD_TOOLS: dict[str, Any] = {
    "blue_cell_scan": blue_cell_scan,
    "defense_brief": defense_brief,
    "export_attack_navigator": export_attack_navigator,
    "kg_query": kg_query,
    "kg_neighbors": kg_neighbors,
    "kg_stats": kg_stats,
}


_ROLE = "blue_cell"
_RECURSION_LIMIT = 120


def create_blue_cell_agent(
    *,
    # ── Dependencies (injected for testing / library composition) ────
    backend: Any = None,
    llm: Any = None,
    fallback_models: list | None = None,
    # ── langchain-style composition (full replace when provided) ─────
    tools: list[Any] | None = None,
    middleware: list[Any] | None = None,
    system_prompt: str | None = None,
    # ── Tuning ───────────────────────────────────────────────────────
    recursion_limit: int | None = None,
):
    """Build the Blue Cell agent.

    Notes:
      - Read-only: no sandbox bash access (no ``sandbox=`` arg, no
        ``set_sandbox()`` call, no ``SandboxNotification`` slot).
      - ``blue_cell_scan`` resolves the engagement workspace from the
        runnable config / ``DECEPTICON_WORKSPACE_PATH`` and reads
        ``.sessions/`` logs; the agent does not shell out.

    Args:
        backend: deepagents-style filesystem backend. Defaults to
            ``make_agent_backend(build_sandbox_backend())``.
        llm: bound chat model. Defaults to ``LLMFactory().get_model("blue_cell")``.
        fallback_models: passed to ``ModelFallbackMiddleware``. Defaults to
            ``LLMFactory().get_fallback_models("blue_cell")``.
        tools: full tool list — when provided, replaces the standard registry
            entirely. When ``None`` (default), the OSS baseline is built and
            plugin overrides (via ``decepticon.bundles``) are applied.
        middleware: full middleware list — when provided, replaces the OSS slot
            stack entirely. When ``None``, the baseline is assembled with plugin
            slot overrides applied.
        system_prompt: full prompt — when provided, replaces the baseline. When
            ``None``, the standard prompt is loaded and plugin prompt overrides
            are applied.
        recursion_limit: ``with_config({"recursion_limit": ...})`` override.
            Defaults to 120.

    Returns:
        Compiled LangGraph agent.
    """
    if llm is None or fallback_models is None:
        factory = LLMFactory()
        if llm is None:
            llm = factory.get_model(_ROLE)
        if fallback_models is None:
            fallback_models = factory.get_fallback_models(_ROLE)

    # No set_sandbox() here — Blue Cell intentionally has no bash tool.
    sandbox = build_sandbox_backend()

    if backend is None:
        backend = make_agent_backend(sandbox)

    if tools is None:
        tools = build_tools(role=_ROLE, standard_tools=_STANDARD_TOOLS)
    if middleware is None:
        middleware = build_middleware(
            role=_ROLE,
            backend=backend,
            llm=llm,
            fallback_models=fallback_models,
            sandbox=None,  # no SandboxNotification for the read-only Blue Cell
        )
    if system_prompt is None:
        system_prompt = load_prompt(_ROLE, shared=[])

    return create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name=_ROLE,
    ).with_config(
        {
            "recursion_limit": recursion_limit or _RECURSION_LIMIT,
            "callbacks": load_plugin_callbacks(role=_ROLE, backend=backend),
        }
    )


# Module-level graph for LangGraph Platform (langgraph serve)
if is_bundle_enabled("standard"):
    graph = create_blue_cell_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="blue_cell",
    description=(
        "Blue Cell — read-only detection-coverage agent. Replays the "
        "engagement's own activity through the detection ruleset, records "
        "which techniques were caught (with MTTD) as DetectionFired nodes, "
        "and reports the detection gaps (Findings nothing detected). "
        "Run after offensive activity to produce the Defense Brief. "
        "Read-only (no bash)."
    ),
    factory=create_blue_cell_agent,
    parent_agents=("decepticon",),
    bundle="standard",
    priority=90,
)
