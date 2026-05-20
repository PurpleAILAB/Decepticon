"""Canonical Prometheus metric names emitted by Decepticon agents.

This module centralizes the metric naming convention so:
1. Grafana dashboards (in containers/observability/grafana-provisioning)
   reference the exact same names agents emit.
2. Agents don't drift apart on label cardinality.
3. New agents/middleware can be wired in seconds via the pre-built
   accessor functions.

All metrics follow the convention ``decepticon_<domain>_<thing>_<unit>``
matching the Prometheus naming guide. Counters end in ``_total``;
histograms have ``_ms``, ``_seconds`` or similar unit suffix.

Standard labels:
- ``engagement``: engagement slug (set by EngagementContextMiddleware)
- ``agent``: agent identifier (decepticon, recon, exploit, ...)
- ``tool``: tool name (curl, nuclei, sqlmap, ...)

Read by dashboards:
- 01-engagement-overview.json
- 02-tool-call-detail.json
- 03-llm-cost.json
- 04-vaccine-pipeline.json
- 05-agent-handoffs.json
"""

from __future__ import annotations

from decepticon.core.telemetry import counter, histogram

# ── canonical metric instances ────────────────────────────────────────
#
# All instances are created lazily on first import — if telemetry isn't
# initialized yet, ``counter()``/``histogram()`` return _NoOpInstrument.

TOOL_CALLS = counter(
    "decepticon_tool_calls_total",
    description="Tool invocations. Labels: engagement, agent, tool, status",
    unit="1",
)

TOOL_LATENCY_MS = histogram(
    "decepticon_tool_latency_ms",
    description="Tool execution wall-clock latency. Labels: engagement, agent, tool",
    unit="ms",
)

AGENT_DISPATCHES = counter(
    "decepticon_agent_dispatches_total",
    description="Sub-agent task() dispatches. Labels: engagement, parent, agent",
    unit="1",
)

AGENT_LATENCY_MS = histogram(
    "decepticon_agent_latency_ms",
    description="Per-agent per-turn wall-clock latency. Labels: engagement, agent",
    unit="ms",
)

FINDING_OUTCOMES = counter(
    "decepticon_finding_outcomes_total",
    description="Finding outcomes by terminal status. Labels: engagement, agent, status (passed|blocked|false_positive)",
    unit="1",
)

VACCINE_STAGE_TRANSITIONS = counter(
    "decepticon_vaccine_stage_transitions_total",
    description="Vaccine pipeline stage flips. Labels: engagement, stage (validated|patched|defended|shipped), bug_class",
    unit="1",
)

VACCINE_DWELL_TIME = histogram(
    "decepticon_vaccine_dwell_time_seconds",
    description="Time spent in each pipeline stage. Labels: engagement, stage",
    unit="s",
)

LLM_TOKENS = counter(
    "decepticon_llm_tokens_total",
    description="LLM tokens consumed. Labels: engagement, agent, model, type (in|out)",
    unit="1",
)

LLM_COST_USD = counter(
    "decepticon_llm_cost_usd_total",
    description="LLM USD cost. Labels: engagement, agent, model",
    unit="USD",
)


# ── helper functions ──────────────────────────────────────────────────


def record_tool_call(
    *,
    engagement: str,
    agent: str,
    tool: str,
    status: str = "ok",
    latency_ms: float | None = None,
) -> None:
    """One-shot helper for tool wrappers."""
    labels = {"engagement": engagement, "agent": agent, "tool": tool, "status": status}
    TOOL_CALLS.add(1, attributes=labels)
    if latency_ms is not None:
        TOOL_LATENCY_MS.record(
            latency_ms,
            attributes={"engagement": engagement, "agent": agent, "tool": tool},
        )


def record_agent_dispatch(
    *,
    engagement: str,
    parent: str,
    agent: str,
    latency_ms: float | None = None,
) -> None:
    """One-shot helper for orchestrator task() dispatches."""
    AGENT_DISPATCHES.add(
        1,
        attributes={"engagement": engagement, "parent": parent, "agent": agent},
    )
    if latency_ms is not None:
        AGENT_LATENCY_MS.record(
            latency_ms,
            attributes={"engagement": engagement, "agent": agent},
        )


def record_finding_outcome(
    *,
    engagement: str,
    agent: str,
    status: str,
) -> None:
    """status ∈ {passed, blocked, false_positive}."""
    FINDING_OUTCOMES.add(
        1,
        attributes={"engagement": engagement, "agent": agent, "status": status},
    )


def record_vaccine_transition(
    *,
    engagement: str,
    stage: str,
    bug_class: str = "unknown",
    dwell_time_s: float | None = None,
) -> None:
    """stage ∈ {validated, patched, defended, shipped}.

    Best called from VaccineWriter._transition after a successful write.
    """
    VACCINE_STAGE_TRANSITIONS.add(
        1,
        attributes={"engagement": engagement, "stage": stage, "bug_class": bug_class},
    )
    if dwell_time_s is not None:
        VACCINE_DWELL_TIME.record(
            dwell_time_s,
            attributes={"engagement": engagement, "stage": stage},
        )


def record_llm_usage(
    *,
    engagement: str,
    agent: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> None:
    """Best called from a LangChain callback or model-fallback wrapper."""
    base = {"engagement": engagement, "agent": agent, "model": model}
    LLM_TOKENS.add(tokens_in, attributes={**base, "type": "in"})
    LLM_TOKENS.add(tokens_out, attributes={**base, "type": "out"})
    LLM_COST_USD.add(cost_usd, attributes=base)


__all__ = [
    "TOOL_CALLS",
    "TOOL_LATENCY_MS",
    "AGENT_DISPATCHES",
    "AGENT_LATENCY_MS",
    "FINDING_OUTCOMES",
    "VACCINE_STAGE_TRANSITIONS",
    "VACCINE_DWELL_TIME",
    "LLM_TOKENS",
    "LLM_COST_USD",
    "record_tool_call",
    "record_agent_dispatch",
    "record_finding_outcome",
    "record_vaccine_transition",
    "record_llm_usage",
]
