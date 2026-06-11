"""LangChain ``@tool`` wrappers for the opscontrol daemon.

These are scoped to the orchestrator (``decepticon`` agent) per
ADR-0006 §2 — specialist sub-agents intentionally do not carry them,
so a prompt-injection in a sub-agent cannot spin up unrelated
infrastructure.

Sprint 1 ships ``ops_start`` / ``ops_stop`` / ``ops_status``. The
engagement-scoped bulk cleanup tool (``ops_cleanup_engagement``)
lands together with the Sprint 2 orchestrator prompt update — Sprint
1 only records the engagement tag in the daemon registry.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.ops.client import (
    OpsControlClient,
    OpsControlError,
    OpsControlUnreachableError,
)

try:
    from langgraph.config import get_config as _lg_get_config
except ImportError:  # langgraph not installed (standalone library use)
    _lg_get_config = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


def _envelope(payload: dict[str, Any]) -> str:
    """Stable JSON envelope so the agent can parse without surprises."""
    return json.dumps(payload, sort_keys=True, default=str)


def _diagnose_unreachable(exc: OpsControlUnreachableError) -> str:
    return _envelope(
        {
            "error": "opscontrol_unreachable",
            "message": str(exc),
            "hint": (
                "The opscontrol daemon owns the docker socket per ADR-0006. "
                "If you reached this from `make dev` / `make smoke` the stack "
                "is daemon-less by design — bring it up via `decepticon start` "
                "to enable workload spawning."
            ),
        }
    )


def _diagnose_http(exc: OpsControlError) -> str:
    return _envelope(
        {
            "error": "opscontrol_http_error",
            "status_code": exc.status_code,
            "body": exc.body,
        }
    )


def _current_engagement() -> str | None:
    """Resolve the engagement slug for the current LangGraph run.

    Pulls from the per-run RunnableConfig via ``langgraph.config.get_config()``
    (the CLI / Web / launcher pass the operator-chosen engagement as
    ``config.configurable.engagement_name`` on every LangGraph run — same
    channel ``EngagementContextMiddleware`` hydrates from). Reading it
    here keeps workloads tagged thread-scoped instead of process-scoped,
    which is the only way one langgraph process can serve multiple
    engagements concurrently.

    Falls back to the ``DECEPTICON_ENGAGEMENT`` env for daemon-less
    library use and the standalone pytest harness; production wiring
    never depends on the env.
    """
    if _lg_get_config is not None:
        try:
            cfg = _lg_get_config() or {}
            configurable = cfg.get("configurable") or {}
            if isinstance(configurable, dict):
                slug = configurable.get("engagement_name")
                if isinstance(slug, str) and slug.strip():
                    return slug.strip()
        except RuntimeError:
            # Called outside a LangGraph runnable context — fall through
            # to the env-based last resort.
            pass
    fallback = os.environ.get("DECEPTICON_ENGAGEMENT") or None
    return fallback


@tool
def ops_start(workload: str) -> str:
    """Spawn a domain-specific workload (BHCE, Sliver C2, …).

    Call this BEFORE delegating to the specialist that needs the
    workload. ``workload`` must be one of the ADR-0006 catalog names
    (``ad``, ``c2-sliver``, ``c2-havoc``, ``reversing``, …). The daemon
    enforces an allowlist server-side — unknown names return a 400.

    The current engagement slug is attached AUTOMATICALLY from the
    LangGraph run's ``config.configurable.engagement_name`` (set by the
    CLI / Web / launcher when opening the thread). The agent must NEVER
    thread an engagement argument through — the tool reads the per-run
    config so workloads are tagged thread-scoped.

    Returns a JSON envelope:
        ``{"workload": "ad", "state": "running", "engagement_id": "..."}``
    or an error envelope on failure.
    """
    engagement_id = _current_engagement()
    try:
        return _envelope(OpsControlClient().start(workload, engagement_id))
    except OpsControlUnreachableError as exc:
        return _diagnose_unreachable(exc)
    except OpsControlError as exc:
        return _diagnose_http(exc)


@tool
def ops_stop(workload: str) -> str:
    """Tear down a previously started workload.

    Call this after the specialist that needed the workload returns,
    unless another pending task in the OPPLAN still needs it. The daemon
    treats stop as idempotent — stopping a stopped workload returns
    202.
    """
    try:
        return _envelope(OpsControlClient().stop(workload))
    except OpsControlUnreachableError as exc:
        return _diagnose_unreachable(exc)
    except OpsControlError as exc:
        return _diagnose_http(exc)


@tool
def ops_cleanup_engagement() -> str:
    """Stop every workload tagged with the current engagement.

    Call this once at engagement close — typically after the final
    report has been written but before the orchestrator returns its
    completion summary. The daemon walks its registry and issues
    ``stop`` for every workload whose ``engagement_id`` field matches
    the active engagement. Idempotent: an already-stopped workload is
    reported in ``stopped`` exactly once.

    The engagement slug is sourced automatically from the LangGraph
    run's ``config.configurable.engagement_name`` (set by the CLI / Web
    / launcher when opening the thread); the orchestrator must NEVER
    pass an engagement argument through.

    Returns a JSON envelope:
        ``{"engagement": "eng-...", "stopped": ["ad", "c2-sliver"], "errors": {...}}``
    or an error envelope on failure.
    """
    engagement_id = _current_engagement()
    if not engagement_id:
        return _envelope(
            {
                "error": "missing_engagement_id",
                "hint": (
                    "ops_cleanup_engagement could not resolve the current "
                    "engagement. The CLI / Web / launcher must set "
                    "`configurable.engagement_name` on the LangGraph run."
                ),
            }
        )
    try:
        return _envelope(OpsControlClient().cleanup_engagement(engagement_id))
    except OpsControlUnreachableError as exc:
        return _diagnose_unreachable(exc)
    except OpsControlError as exc:
        return _diagnose_http(exc)


@tool
def ops_status() -> str:
    """List every workload the opscontrol daemon has touched this session.

    Returns a JSON envelope:
        ``{"backend": "docker-compose", "allowlist": [...],
           "workloads": [{"workload": "ad", "state": "running",
                          "engagement_id": "...", "since": "..."}]}``
    or an error envelope on failure.
    """
    try:
        client = OpsControlClient()
        health = client.health()
        workloads = client.list_profiles()
        return _envelope(
            {
                "backend": health.get("backend"),
                "allowlist": health.get("allowlist", []),
                "workloads": workloads,
            }
        )
    except OpsControlUnreachableError as exc:
        return _diagnose_unreachable(exc)
    except OpsControlError as exc:
        return _diagnose_http(exc)


OPS_TOOLS = [ops_start, ops_stop, ops_cleanup_engagement, ops_status]
