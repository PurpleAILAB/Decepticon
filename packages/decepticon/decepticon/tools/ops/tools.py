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


@tool
def ops_start(workload: str, engagement_id: str | None = None) -> str:
    """Spawn a domain-specific workload (BHCE, Sliver C2, …).

    Call this BEFORE delegating to the specialist that needs the
    workload. ``workload`` must be one of the ADR-0006 catalog names
    (``ad``, ``c2-sliver``, ``c2-havoc``, ``reversing``, …). The daemon
    enforces an allowlist server-side — unknown names return a 400.

    ``engagement_id`` tags the workload so the daemon registry can
    associate it with the current engagement. If omitted, the tool
    reads ``DECEPTICON_ENGAGEMENT`` from the langgraph env (set by the
    launcher's engagement picker).

    Returns a JSON envelope:
        ``{"workload": "ad", "state": "running", "engagement_id": "..."}``
    or an error envelope on failure.
    """
    if engagement_id is None:
        engagement_id = os.environ.get("DECEPTICON_ENGAGEMENT") or None
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


OPS_TOOLS = [ops_start, ops_stop, ops_status]
