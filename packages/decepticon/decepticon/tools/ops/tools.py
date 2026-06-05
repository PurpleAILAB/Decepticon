"""LangChain ``@tool`` wrappers for the ops-control sidecar.

ADR-0006.  Three composite tools the orchestrator agent uses to bring
domain-specific sidecars up/down at runtime:

  - ``ops_start(profile)`` — docker compose --profile <name> up -d
  - ``ops_stop(profile)``  — docker compose --profile <name> stop
  - ``ops_status()``       — current allowlist + running services

The actual docker-socket interaction lives inside the ops-control
container, not here.  langgraph reaches ops-control over HTTP on
``decepticon-net``; it has no Docker access of its own.

These tools belong on the orchestrator's toolbox only.  Specialist
sub-agents (ad_operator, c2_operator, …) must not import this module.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.ops.client import (
    OpsControlClient,
    OpsControlConfigError,
    OpsControlHTTPError,
)

log = logging.getLogger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _make_client() -> OpsControlClient | None:
    try:
        return OpsControlClient.from_env()
    except OpsControlConfigError as exc:
        log.warning("ops-control client unavailable: %s", exc)
        return None


def _config_error(message: str) -> str:
    return _json(
        {
            "error": message,
            "hint": (
                "Set OPS_CONTROL_URL on the langgraph container (e.g. "
                "http://ops-control:8090).  See ADR-0006."
            ),
        }
    )


# ── ops_start ──────────────────────────────────────────────────────


@tool
def ops_start(profile: str) -> str:
    """Bring a domain-specific compose profile up.

    Use this before delegating to a specialist whose domain needs a
    sidecar service — e.g. call ``ops_start("ad")`` before delegating
    to ``ad_operator`` so BHCE is healthy by the time the specialist
    issues its first tool call.  Idempotent: re-issuing on an already
    running profile is a no-op.

    Args:
        profile: Compose profile name on the server-side allowlist.
    """
    if not profile or not profile.strip():
        return _json({"error": "profile is required"})
    client = _make_client()
    if client is None:
        return _config_error("OpsControlClient could not be constructed from env")
    try:
        with client:
            return _json(client.start_profile(profile.strip()))
    except OpsControlHTTPError as exc:
        return _json(
            {
                "error": "ops-control returned an error on start",
                "status_code": exc.status_code,
                "body": exc.body,
            }
        )


# ── ops_stop ───────────────────────────────────────────────────────


@tool
def ops_stop(profile: str) -> str:
    """Stop a domain-specific compose profile.

    Call once the specialist has returned and no pending OPPLAN task
    still needs that domain.  ``stop`` keeps volumes and containers
    around so the next ``ops_start`` is fast.

    Args:
        profile: Compose profile name on the server-side allowlist.
    """
    if not profile or not profile.strip():
        return _json({"error": "profile is required"})
    client = _make_client()
    if client is None:
        return _config_error("OpsControlClient could not be constructed from env")
    try:
        with client:
            return _json(client.stop_profile(profile.strip()))
    except OpsControlHTTPError as exc:
        return _json(
            {
                "error": "ops-control returned an error on stop",
                "status_code": exc.status_code,
                "body": exc.body,
            }
        )


# ── ops_status ─────────────────────────────────────────────────────


@tool
def ops_status() -> str:
    """List the ops-control allowlist and currently-running profiles.

    Use this to confirm a profile is actually live before issuing
    domain-specific tools, or to decide whether ``ops_stop`` is
    needed at the end of an objective.
    """
    client = _make_client()
    if client is None:
        return _config_error("OpsControlClient could not be constructed from env")
    try:
        with client:
            return _json({"health": client.health(), "profiles": client.list_profiles()})
    except OpsControlHTTPError as exc:
        return _json(
            {
                "error": "ops-control returned an error on status",
                "status_code": exc.status_code,
                "body": exc.body,
            }
        )


OPS_TOOLS = [ops_start, ops_stop, ops_status]
"""Wire into the orchestrator agent's toolbox.  Specialists never see
these — agent-level gating is what keeps a compromised sub-agent from
spinning up infrastructure outside its domain."""
