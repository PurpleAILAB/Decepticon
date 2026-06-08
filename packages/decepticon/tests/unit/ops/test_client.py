"""Unit tests for ``decepticon.tools.ops.client``.

We exercise the client against an :class:`httpx.MockTransport` rather
than a real UDS so the tests run anywhere — including CI runners
where ``/var/run`` is read-only and Unix-socket binds may not be
permitted. The transport substitution matches the convention used by
``tests/unit/ad/test_bh_tools.py``.
"""

from __future__ import annotations

import json

import httpx
import pytest

from decepticon.tools.ops.client import (
    OpsControlClient,
    OpsControlError,
    OpsControlUnreachableError,
)


def _client_with_mock(handler):
    client = OpsControlClient(socket_path="/tmp/unused.sock")
    # Patch the internal _client factory to return a MockTransport-backed
    # httpx.Client, bypassing the UDS transport that real-mode would
    # use. Tests that need to assert the UDS path is wired into
    # httpx.HTTPTransport directly should stub _client differently.
    client._client = lambda: httpx.Client(  # type: ignore[method-assign]
        base_url="http://opscontrol",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_health_returns_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/health"
        return httpx.Response(200, json={"ok": True, "backend": "fake", "allowlist": ["ad"]})

    client = _client_with_mock(handler)
    assert client.health() == {"ok": True, "backend": "fake", "allowlist": ["ad"]}


def test_start_propagates_engagement_query_param() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = request.url.params.get("engagement")
        return httpx.Response(202, json={"workload": "ad", "state": "running"})

    client = _client_with_mock(handler)
    out = client.start("ad", engagement_id="eng-99")
    assert out == {"workload": "ad", "state": "running"}
    assert seen["path"] == "/v1/profiles/ad/start"
    assert seen["query"] == "eng-99"


def test_start_omits_query_when_engagement_blank() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.query
        return httpx.Response(202, json={"workload": "ad", "state": "running"})

    client = _client_with_mock(handler)
    client.start("ad")
    assert seen["query"] == b""


def test_stop_hits_stop_endpoint() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(202, json={"workload": "ad", "state": "stopped"})

    client = _client_with_mock(handler)
    client.stop("ad")
    assert seen["path"] == "/v1/profiles/ad/stop"


def test_list_profiles_returns_list() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"workload": "ad", "state": "running"}])

    client = _client_with_mock(handler)
    assert client.list_profiles() == [{"workload": "ad", "state": "running"}]


def test_http_error_is_raised() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "not in allowlist"})

    client = _client_with_mock(handler)
    with pytest.raises(OpsControlError) as exc_info:
        client.start("bogus")
    assert exc_info.value.status_code == 400
    assert "not in allowlist" in json.dumps(exc_info.value.body)


def test_unreachable_when_socket_missing(tmp_path) -> None:
    bogus = tmp_path / "missing.sock"
    client = OpsControlClient(socket_path=str(bogus))
    with pytest.raises(OpsControlUnreachableError):
        client.health()
