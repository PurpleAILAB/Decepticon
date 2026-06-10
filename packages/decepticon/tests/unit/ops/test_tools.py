"""Unit tests for the ``ops_start`` / ``ops_stop`` / ``ops_status`` tools.

We monkeypatch :class:`OpsControlClient` so the tool layer can be
exercised without a daemon. The goal is to confirm the envelope shape
(`error`, `hint`, JSON-serializable payloads) that the orchestrator
agent will eventually parse.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from decepticon.tools.ops import (
    OPS_TOOLS,
    ops_cleanup_engagement,
    ops_start,
    ops_status,
    ops_stop,
)
from decepticon.tools.ops.client import OpsControlError, OpsControlUnreachableError


class _FakeClient:
    def __init__(
        self, *, health=None, profiles=None, start_result=None, stop_result=None, raise_on=None
    ):
        self._health = health or {"ok": True, "backend": "fake", "allowlist": ["ad"]}
        self._profiles = profiles or []
        self._start = start_result or {"workload": "ad", "state": "running"}
        self._stop = stop_result or {"workload": "ad", "state": "stopped"}
        self._raise = raise_on or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _maybe_raise(self, method: str) -> None:
        exc = self._raise.get(method)
        if exc is not None:
            raise exc

    def health(self):
        self._maybe_raise("health")
        return self._health

    def list_profiles(self):
        self._maybe_raise("list_profiles")
        return self._profiles

    def start(self, workload, engagement_id=None):
        self.calls.append(("start", {"workload": workload, "engagement_id": engagement_id}))
        self._maybe_raise("start")
        return self._start

    def stop(self, workload):
        self.calls.append(("stop", {"workload": workload}))
        self._maybe_raise("stop")
        return self._stop

    def cleanup_engagement(self, engagement_id):
        self.calls.append(("cleanup_engagement", {"engagement_id": engagement_id}))
        self._maybe_raise("cleanup_engagement")
        return {"engagement": engagement_id, "stopped": ["ad", "c2-sliver"]}


@pytest.fixture
def patch_client(monkeypatch):
    fake = _FakeClient()

    def factory(*_args, **_kwargs):
        return fake

    monkeypatch.setattr("decepticon.tools.ops.tools.OpsControlClient", factory)
    return fake


def test_ops_start_returns_envelope(patch_client) -> None:
    # Engagement now travels via config.configurable.engagement_name —
    # the same channel EngagementContextMiddleware reads — so the tool
    # is thread-scoped and one langgraph process can serve multiple
    # engagements concurrently.
    out = ops_start.invoke(
        {"workload": "ad"},
        config={"configurable": {"engagement_name": "eng-1"}},
    )
    data = json.loads(out)
    assert data == {"state": "running", "workload": "ad"}
    assert patch_client.calls[0] == ("start", {"workload": "ad", "engagement_id": "eng-1"})


def test_ops_start_pulls_engagement_from_env(monkeypatch, patch_client) -> None:
    # Env is a last-resort fallback for the daemon-less library path
    # and pytest fixtures; production wiring goes through the per-run
    # config.
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT", "eng-from-env")
    ops_start.invoke({"workload": "ad"})
    assert patch_client.calls[0][1]["engagement_id"] == "eng-from-env"


def test_ops_start_config_wins_over_env(monkeypatch, patch_client) -> None:
    # When the operator runs two concurrent threads against the same
    # langgraph process, each thread must see its own
    # config.configurable.engagement_name — the process-wide env
    # cannot be the source of truth.
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT", "eng-from-env")
    ops_start.invoke(
        {"workload": "ad"},
        config={"configurable": {"engagement_name": "eng-from-config"}},
    )
    assert patch_client.calls[0][1]["engagement_id"] == "eng-from-config"


def test_ops_start_unreachable_diagnostic(monkeypatch) -> None:
    # Patch the factory so the tool sees an immediate construction-time
    # error — equivalent to "no socket file at the default path".
    monkeypatch.setattr(
        "decepticon.tools.ops.tools.OpsControlClient",
        lambda *_a, **_k: type(
            "X",
            (),
            {
                "start": lambda self, *_args, **_kw: (_ for _ in ()).throw(
                    OpsControlUnreachableError("missing")
                ),
            },
        )(),
    )
    out = ops_start.invoke({"workload": "ad"})
    data = json.loads(out)
    assert data["error"] == "opscontrol_unreachable"
    assert "ADR-0006" in data["hint"]


def test_ops_start_http_error_propagates(monkeypatch) -> None:
    def factory(*_a, **_k):
        class C:
            def start(self, *_args, **_kw):
                raise OpsControlError(400, {"error": "not in allowlist"})

        return C()

    monkeypatch.setattr("decepticon.tools.ops.tools.OpsControlClient", factory)
    out = ops_start.invoke({"workload": "bogus"})
    data = json.loads(out)
    assert data["error"] == "opscontrol_http_error"
    assert data["status_code"] == 400


def test_ops_stop_returns_envelope(patch_client) -> None:
    out = ops_stop.invoke({"workload": "ad"})
    data = json.loads(out)
    assert data == {"state": "stopped", "workload": "ad"}
    assert patch_client.calls[0] == ("stop", {"workload": "ad"})


def test_ops_status_merges_health_and_profiles(patch_client) -> None:
    patch_client._profiles = [{"workload": "ad", "state": "running", "engagement_id": "eng-x"}]
    out = ops_status.invoke({})
    data = json.loads(out)
    assert data["backend"] == "fake"
    assert data["allowlist"] == ["ad"]
    assert data["workloads"][0]["workload"] == "ad"


def test_ops_cleanup_engagement_returns_envelope(patch_client) -> None:
    out = ops_cleanup_engagement.invoke(
        {},
        config={"configurable": {"engagement_name": "eng-99"}},
    )
    data = json.loads(out)
    assert data == {"engagement": "eng-99", "stopped": ["ad", "c2-sliver"]}
    assert patch_client.calls[0] == ("cleanup_engagement", {"engagement_id": "eng-99"})


def test_ops_cleanup_engagement_pulls_from_env(monkeypatch, patch_client) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT", "eng-from-env")
    ops_cleanup_engagement.invoke({})
    assert patch_client.calls[0][1]["engagement_id"] == "eng-from-env"


def test_ops_cleanup_engagement_requires_engagement(monkeypatch) -> None:
    monkeypatch.delenv("DECEPTICON_ENGAGEMENT", raising=False)
    out = ops_cleanup_engagement.invoke({})
    data = json.loads(out)
    # No id provided and env unset — the tool must surface a clear
    # diagnostic rather than calling the daemon with the empty string.
    assert data["error"] == "missing_engagement_id"


def test_tools_registered_in_OPS_TOOLS() -> None:
    names = {t.name for t in OPS_TOOLS}
    assert names == {"ops_start", "ops_stop", "ops_cleanup_engagement", "ops_status"}
