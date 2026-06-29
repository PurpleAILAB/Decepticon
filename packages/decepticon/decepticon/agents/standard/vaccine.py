"""Offensive Vaccine Agent — attack→defend→verify closed-loop hardening.

The Vaccine agent embodies the *Offensive Vaccine* philosophy: every confirmed
vulnerability discovered by the Red Cell becomes the starting point for a
defensive remediation cycle.  The agent:

1. **Generates a remediation brief** — translates each Finding into a
   prioritised, actionable mitigation plan with concrete configuration or
   code-level fixes.
2. **Applies the defense** — deploys compensating controls, patches, or
   detection rules via ``apply_defense``, recording each action as a
   ``DefenseAction`` node linked to its Finding.
3. **Verifies the defense** — re-executes the original attack vector (or a
   validated equivalent) to prove the mitigation is effective, recording
   ``VerificationResult`` nodes with pass/fail disposition and evidence.

This loop runs iteratively: a failed verification feeds back into
remediation re-planning until coverage is proven or the engagement's
time-box expires.

Design choices — enforced by tool surface:

- **Write-capable (defense only).**  The agent can deploy defences and
  re-run attack verification, but cannot discover *new* attack surface.
  New findings come from the Red Cell / Operator.
- **KG-linked.**  Every tool writes structured nodes/edges so the Blue
  Cell and Defense Brief can account for vaccine-driven mitigations in
  the coverage report.
- **Middleware-injected state.**  ``VaccineStateMiddleware`` injects the
  current engagement's unmitigated findings, prior defense actions, and
  verification history into each turn so the LLM has full situational
  awareness without extra KG queries.

Library API
-----------
Factory shape mirrors ``langchain.agents.create_agent`` /
``deepagents.create_deep_agent``:

  - ``tools=[...]``         full tool list (overrides the standard set)
  - ``middleware=[...]``    full middleware list (overrides the slot stack)
  - ``system_prompt="..."`` full prompt (overrides the loaded baseline)

When a keyword is ``None`` (default), the factory builds the OSS baseline AND
applies any plugin overrides discovered via the ``decepticon.bundles``
entry-point group.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from decepticon.agents.build import build_middleware, build_tools
from decepticon.agents.prompts import load_prompt
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.middleware.vaccine import VaccineStateMiddleware
from decepticon.tools.research.tools import kg_neighbors, kg_query, kg_stats
from decepticon.tools.vaccine.tools import (
    apply_defense,
    generate_remediation_brief,
    record_vaccine_result,
    verify_defense,
)
from decepticon_core.plugin_loader import (
    SubAgentSpec,
    is_bundle_enabled,
    load_plugin_callbacks,
)

_STANDARD_TOOLS: dict[str, Any] = {
    "generate_remediation_brief": generate_remediation_brief,
    "apply_defense": apply_defense,
    "verify_defense": verify_defense,
    "record_vaccine_result": record_vaccine_result,
    "kg_query": kg_query,
    "kg_neighbors": kg_neighbors,
    "kg_stats": kg_stats,
}

_ROLE = "vaccine"
_RECURSION_LIMIT = 150

_SYSTEM_PROMPT_SHARED = [
    "You are the Offensive Vaccine agent. Your mission is to close the loop "
    "between offensive discovery and defensive hardening.\n\n"
    "## Operating Loop\n\n"
    "1. **Assess** — Review unmitigated Findings from the engagement's "
    "knowledge graph. Prioritise by severity, exploitability, and blast "
    "radius.\n"
    "2. **Remediate** — For each Finding, call `generate_remediation_brief` to "
    "produce a structured mitigation plan. Then call `apply_defense` to deploy "
    "the compensating control, patch, or detection rule.\n"
    "3. **Verify** — Call `verify_defense` to re-execute the original attack "
    "vector against the patched target. If the attack still succeeds, iterate "
    "on the defense; if it fails (defense holds), record the proven mitigation "
    "with `record_vaccine_result`.\n"
    "4. **Report** — After all Findings are addressed (or time-boxed), "
    "summarise coverage: how many Findings were mitigated, how many remain, "
    "and residual risk.\n\n"
    "## Constraints\n\n"
    "- NEVER discover new attack surface. You harden what the Red Cell found.\n"
    "- ALWAYS record every action in the knowledge graph so Blue Cell and the "
    "Defense Brief reflect your work.\n"
    "- A defense is NOT proven until `verify_defense` confirms the original "
    "vector is blocked.\n"
    "- Prefer minimal, targeted fixes over sweeping changes.\n"
    "- When a fix fails verification, analyse *why* it failed before retrying.",
]


def create_vaccine_agent(
    *,
    # ── Dependencies (injected for testing / library composition) ────
    backend: Any = None,
    llm: Any = None,
    fallback_models: list[Any] | None = None,
    # ── langchain-style composition (full replace when provided) ─────
    tools: list[Any] | None = None,
    middleware: list[Any] | None = None,
    system_prompt: str | None = None,
    # ── Tuning ───────────────────────────────────────────────────────
    recursion_limit: int | None = None,
) -> Any:
    """Build the Offensive Vaccine agent.

    The agent has sandbox access for deploying defences and re-running
    attack verification, but its tool surface is scoped to remediation —
    no new-vulnerability discovery tools are included.

    Args:
        backend: deepagents-style filesystem backend.  Defaults to
            ``make_agent_backend(build_sandbox_backend())``.
        llm: bound chat model.  Defaults to
            ``LLMFactory().get_model("vaccine")``.
        fallback_models: passed to ``ModelFallbackMiddleware``.  Defaults
            to ``LLMFactory().get_fallback_models("vaccine")``.
        tools: full tool list — replaces the standard registry when
            provided.  ``None`` builds the OSS baseline with plugin
            overrides.
        middleware: full middleware list — replaces the slot stack when
            provided.  ``None`` assembles the baseline with plugin
            overrides plus ``VaccineStateMiddleware``.
        system_prompt: full prompt — replaces the baseline when provided.
            ``None`` loads the standard prompt with shared fragments.
        recursion_limit: ``with_config({"recursion_limit": ...})``
            override.  Defaults to 150 (higher than Blue Cell because
            the attack→defend→verify loop can require many iterations).

    Returns:
        Compiled LangGraph agent.
    """
    if llm is None or fallback_models is None:
        factory = LLMFactory()
        if llm is None:
            llm = factory.get_model(_ROLE)
        if fallback_models is None:
            fallback_models = factory.get_fallback_models(_ROLE)

    sandbox = build_sandbox_backend()

    if backend is None:
        backend = make_agent_backend(sandbox)

    if tools is None:
        tools = build_tools(role=_ROLE, standard_tools=_STANDARD_TOOLS)
    if middleware is None:
        base_middleware = build_middleware(
            role=_ROLE,
            backend=backend,
            llm=llm,
            fallback_models=fallback_models,
            sandbox=sandbox,
        )
        # Inject vaccine-specific state middleware at the front so every
        # turn begins with fresh situational awareness.
        base_middleware.insert(0, VaccineStateMiddleware(backend=backend))
        middleware = base_middleware
    if system_prompt is None:
        system_prompt = load_prompt(_ROLE, shared=_SYSTEM_PROMPT_SHARED)

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
    graph = create_vaccine_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="vaccine",
    description=(
        "Offensive Vaccine — closed-loop hardening agent.  Takes confirmed "
        "Findings from the Red Cell, generates remediation briefs, deploys "
        "compensating controls, and re-runs the original attack vector to "
        "verify defences hold.  Records Mitigation, DefenseAction, and "
        "VerificationResult nodes in the knowledge graph so the Defense "
        "Brief reflects proven coverage."
    ),
    factory=create_vaccine_agent,
    parent_agents=("decepticon",),
    bundle="standard",
    priority=85,
)
