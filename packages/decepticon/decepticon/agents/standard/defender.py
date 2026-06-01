"""Defender Agent — deploys detections to the customer's SIEM/EDR.

The Offensive Vaccine pipeline's final stage. Blue Cell *measures* detection
coverage and surfaces gaps (``agents/standard/blue_cell.py``); the Defender
*closes* them: it reads the engagement's Findings and detection gaps from the
knowledge graph, authors Sigma / YARA rules for the uncovered techniques, and
deploys them to the customer's stack via ``DEFENSE_TOOLS`` — Splunk saved
searches, Sentinel analytic rules, Elastic detection rules, Defender XDR custom
detections, and CrowdStrike IOAs. Each deployed rule is recorded as a
``DefenseAction`` node so a subsequent Blue Cell scan can link a fired
detection back to it (``DetectionFired -[:USES_RULE]-> DefenseAction``).

This is the agent ``tools/defense/`` was built for ("gives Defender + Patcher
agents [the push surface]") and the "Defender" stage ``docs/offensive-vaccine.md``
says was removed and should be rebuilt. See also ``skills/standard/dfir``.

Key design choices — enforced by the tool surface, not just the prompt:

- **No bash, no offensive tools.** Detection deployment is HTTP-only; the
  ``sigma_to_*`` tools convert Sigma → SPL/KQL/Lucene internally. The Defender
  never touches the target.
- **HITL-gated writes.** Every ``sigma_to_*`` / ``yara_to_*`` call writes to
  the *customer's* production SIEM/EDR, so they sit behind the operator-
  approval gate (``middleware/hitl.py``); ``SLOTS_PER_ROLE["defender"]``
  therefore includes ``HITL_APPROVAL``. The push tools also prefix every rule
  with ``decepticon-eng-<slug>::`` for blue-team revocation, which needs
  ``ENGAGEMENT_CONTEXT``.

  IMPORTANT: HITL is opt-in product-wide — ``HITL_APPROVAL`` resolves to a
  no-op unless ``DECEPTICON_HITL__ENABLED`` is truthy (``_make_hitl`` returns
  ``None`` otherwise). So on a default engagement these customer-SIEM writes
  run **without** an approval prompt. Set ``DECEPTICON_HITL__ENABLED=true``
  to make the gate effective before running the Defender against a real
  customer environment.

Library API mirrors ``langchain.agents.create_agent``: every keyword is
optional and explicit values fully replace the OSS baseline (see the other
standard factories for the three convergent usage paths).
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from decepticon.agents.build import build_middleware, build_tools
from decepticon.agents.prompts import load_prompt
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.tools.defense import DEFENSE_TOOLS
from decepticon.tools.research.tools import kg_add_node, kg_neighbors, kg_query, kg_stats
from decepticon_core.plugin_loader import SubAgentSpec, is_bundle_enabled, load_plugin_callbacks

# Name-keyed baseline tools: the SIEM/EDR push surface plus the KG read subset
# and node-write (to record DefenseAction artifacts). No bash, no attack tools.
_STANDARD_TOOLS: dict[str, Any] = {
    **{tool.name: tool for tool in DEFENSE_TOOLS},
    "kg_query": kg_query,
    "kg_neighbors": kg_neighbors,
    "kg_stats": kg_stats,
    "kg_add_node": kg_add_node,
}

# DFIR / loop-closure playbook (the catalog that frames the Defender workflow).
_SKILL_SOURCES: list[str] = [
    "/skills/standard/dfir/",
    "/skills/shared/",
]


_ROLE = "defender"
_RECURSION_LIMIT = 150


def create_defender_agent(
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
    """Build the Defender agent.

    Notes:
      - No bash tool and no ``sandbox=`` arg — detection deployment is HTTP-only
        and the Defender never touches the target.
      - ``sigma_to_*`` / ``yara_to_*`` are HITL-gated (customer-SIEM writes) via
        ``SLOTS_PER_ROLE["defender"]`` including ``HITL_APPROVAL``.

    Args:
        backend: deepagents-style filesystem backend. Defaults to
            ``make_agent_backend(build_sandbox_backend())``.
        llm: bound chat model. Defaults to ``LLMFactory().get_model("defender")``.
        fallback_models: passed to ``ModelFallbackMiddleware``. Defaults to
            ``LLMFactory().get_fallback_models("defender")``.
        tools: full tool list — replaces the standard registry when provided.
        middleware: full middleware list — replaces the slot stack when provided.
        system_prompt: full prompt — replaces the baseline when provided.
        recursion_limit: ``with_config`` override. Defaults to 150.

    Returns:
        Compiled LangGraph agent.
    """
    if llm is None or fallback_models is None:
        factory = LLMFactory()
        if llm is None:
            llm = factory.get_model(_ROLE)
        if fallback_models is None:
            fallback_models = factory.get_fallback_models(_ROLE)

    # No set_sandbox() — the Defender intentionally has no bash tool.
    sandbox = build_sandbox_backend()

    if backend is None:
        backend = make_agent_backend(sandbox)

    if tools is None:
        tools = build_tools(role=_ROLE, standard_tools=_STANDARD_TOOLS)
    if middleware is None:
        middleware = build_middleware(
            role=_ROLE,
            skill_sources=_SKILL_SOURCES,
            backend=backend,
            llm=llm,
            fallback_models=fallback_models,
            sandbox=None,  # no SandboxNotification — no bash tool
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
    graph = create_defender_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="defender",
    description=(
        "Defender — deploys detections to the customer SIEM/EDR. Reads "
        "Findings and Blue Cell detection gaps from the graph, authors "
        "Sigma/YARA rules for the uncovered techniques, and pushes them via "
        "Splunk/Sentinel/Elastic/Defender XDR/CrowdStrike (HITL-gated), "
        "recording each as a DefenseAction. Run after Blue Cell to close the "
        "gaps it found. Read-only on the target (no bash)."
    ),
    factory=create_defender_agent,
    parent_agents=("decepticon",),
    bundle="standard",
    priority=95,
)
