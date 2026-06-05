"""Unit tests for the ops-control LangChain @tool surface.

The agent-facing surface is small (3 @tools wrapping 4 HTTP calls),
so the tests focus on:
  - HTTP method + path are 1:1 with the ops-control routes
  - JSON envelopes propagate cleanly through the @tool layer
  - Missing OPS_CONTROL_URL produces an actionable diagnostic
  - HTTP errors from ops-control surface to the agent as structured
    fields (status_code + body) rather than tracebacks

Wire-level docker-compose behaviour is exercised at integration /
dogfood time against the ops-control container itself, not here.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from decepticon.tools.ops.tools import ops_start, ops_status, ops_stop


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_CONTROL_URL", "http://ops-control:8090")


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _fake(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs.pop("timeout", None)
        return real_client(transport=transport, timeout=5.0, *args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _fake)


# ── ops_start ──────────────────────────────────────────────────────


def test_ops_start_hits_correct_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(202, json={"profile": "ad", "action": "started"})

    _install_transport(monkeypatch, handler)
    out = json.loads(ops_start.invoke({"profile": "ad"}))
    assert seen == {"method": "POST", "path": "/v1/profiles/ad/start"}
    assert out["action"] == "started"


def test_ops_start_empty_profile_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    out = json.loads(ops_start.invoke({"profile": "  "}))
    assert "required" in out["error"]


def test_ops_start_propagates_allowlist_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"detail": "profile 'mystery' is not in OPS_PROFILE_ALLOWLIST"},
        )

    _install_transport(monkeypatch, handler)
    out = json.loads(ops_start.invoke({"profile": "mystery"}))
    assert out["status_code"] == 400
    assert "allowlist" in json.dumps(out["body"]).lower()


def test_ops_start_missing_env_returns_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPS_CONTROL_URL", raising=False)
    out = json.loads(ops_start.invoke({"profile": "ad"}))
    assert "OPS_CONTROL_URL" in out["hint"]


# ── ops_stop ───────────────────────────────────────────────────────


def test_ops_stop_hits_correct_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(202, json={"profile": "c2-sliver", "action": "stopped"})

    _install_transport(monkeypatch, handler)
    out = json.loads(ops_stop.invoke({"profile": "c2-sliver"}))
    assert seen == {"method": "POST", "path": "/v1/profiles/c2-sliver/stop"}
    assert out["action"] == "stopped"


def test_ops_stop_empty_profile_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    out = json.loads(ops_stop.invoke({"profile": ""}))
    assert "required" in out["error"]


# ── ops_status ─────────────────────────────────────────────────────


def test_ops_status_combines_health_and_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/health":
            return httpx.Response(200, json={"ok": True, "allowlist_size": 4})
        if request.url.path == "/v1/profiles":
            return httpx.Response(
                200,
                json={"allowlist": ["ad", "c2-sliver"], "running": {"ad": ["bhce=running"]}},
            )
        raise AssertionError(f"unexpected call: {request.url.path}")

    _install_transport(monkeypatch, handler)
    out = json.loads(ops_status.invoke({}))
    assert out["health"]["allowlist_size"] == 4
    assert out["profiles"]["running"]["ad"] == ["bhce=running"]


# ── plumbing ───────────────────────────────────────────────────────


def test_ops_tools_list_exports_three() -> None:
    from decepticon.tools.ops import OPS_TOOLS

    names = sorted(t.name for t in OPS_TOOLS)
    assert names == ["ops_start", "ops_status", "ops_stop"]
