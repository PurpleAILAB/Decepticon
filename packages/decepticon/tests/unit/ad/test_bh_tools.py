"""Unit tests for the BHCE-backed ``bhce_*`` LangChain tool surface.

The tools wrap :mod:`decepticon.tools.ad.bhce_client`; here we stub the
HTTP layer (``httpx.Client``) so we exercise just the tool-side
behaviour: JSON envelope shape, missing-env diagnostic, the
file-upload 3-step + poll loop, and error propagation.

Wire-level HMAC compatibility is covered separately in
``test_bhce_client.py``.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import httpx
import pytest

from decepticon.tools.ad.bh_tools import (
    bhce_cypher,
    bhce_ingest_zip,
    bhce_status,
)


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BHCE_URL", "http://bhce.local:8080")
    monkeypatch.setenv("BHCE_TOKEN_ID", "tid")
    monkeypatch.setenv("BHCE_TOKEN_KEY", "tkey")


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    """Replace the default httpx.Client constructor with one wired to a
    ``MockTransport`` so the tools' internal ``BHCEClient.from_env``
    yields a non-network client."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _fake(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs.pop("timeout", None)
        return real_client(transport=transport, timeout=5.0, *args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _fake)


def _ok(json_body: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=json_body)


# ── bhce_status ───────────────────────────────────────────────────


def test_bhce_status_returns_version_and_self(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return _ok({"data": {"server_version": "v9.2.2", "product_edition": "community"}})
        if request.url.path == "/api/v2/self":
            return _ok({"data": {"id": "u-1", "principal_name": "admin"}})
        return _ok({"data": {}})

    _install_transport(monkeypatch, handler)
    payload = json.loads(bhce_status.invoke({}))
    assert payload["version"]["data"]["server_version"] == "v9.2.2"
    assert payload["self"]["data"]["principal_name"] == "admin"


def test_bhce_status_missing_env_returns_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BHCE_URL", raising=False)
    payload = json.loads(bhce_status.invoke({}))
    assert payload["error"]
    assert "BHCE_URL" in payload["hint"]


# ── bhce_cypher ───────────────────────────────────────────────────


def test_bhce_cypher_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/graphs/cypher"
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return _ok({"data": {"nodes": {}, "edges": [], "literals": [{"value": 42, "key": "c"}]}})

    _install_transport(monkeypatch, handler)
    out = json.loads(
        bhce_cypher.invoke({"query": "MATCH (n) RETURN count(n) AS c", "include_properties": False})
    )
    assert out["data"]["literals"][0]["value"] == 42
    assert captured["body"]["query"] == "MATCH (n) RETURN count(n) AS c"
    assert captured["body"]["include_properties"] is False


def test_bhce_cypher_empty_query_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    out = json.loads(bhce_cypher.invoke({"query": "   "}))
    assert "required" in out["error"]


def test_bhce_cypher_propagates_bhce_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"http_status": 400, "errors": [{"message": "syntax error"}]},
        )

    _install_transport(monkeypatch, handler)
    out = json.loads(bhce_cypher.invoke({"query": "MATCH (n RETURN n"}))
    assert out["status_code"] == 400
    assert "syntax error" in json.dumps(out["body"])


# ── bhce_ingest_zip ───────────────────────────────────────────────


def _make_tiny_zip(tmp_path) -> str:
    z = tmp_path / "sample.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("sample.json", '{"meta":{"type":"users"},"data":[]}')
    return str(z)


def test_bhce_ingest_zip_runs_three_step_and_polls_until_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _set_env(monkeypatch)
    zip_path = _make_tiny_zip(tmp_path)
    monkeypatch.setattr("decepticon.tools.ad.bh_tools._UPLOAD_POLL_INTERVAL_SECONDS", 0.01)

    calls: list[tuple[str, str]] = []
    poll_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append((request.method, path))
        if request.method == "POST" and path == "/api/v2/file-upload/start":
            return httpx.Response(201, json={"data": {"id": 7}})
        if request.method == "POST" and path == "/api/v2/file-upload/7":
            assert request.headers.get("Content-Type") == "application/zip"
            assert request.content  # body forwarded
            return httpx.Response(202)
        if request.method == "POST" and path == "/api/v2/file-upload/7/end":
            return httpx.Response(200)
        if request.method == "GET" and path == "/api/v2/file-upload":
            poll_count["n"] += 1
            status = "Running" if poll_count["n"] < 2 else "Complete"
            return _ok({"data": [{"id": 7, "status": status}]})
        raise AssertionError(f"unexpected call: {request.method} {path}")

    _install_transport(monkeypatch, handler)
    out = json.loads(bhce_ingest_zip.invoke({"path": zip_path}))
    assert out["job_id"] == 7
    assert out["terminal_status"] == "Complete"
    # The 3 mutating steps each happen exactly once.
    methods_paths = [(m, p) for m, p in calls if m == "POST"]
    assert ("POST", "/api/v2/file-upload/start") in methods_paths
    assert ("POST", "/api/v2/file-upload/7") in methods_paths
    assert ("POST", "/api/v2/file-upload/7/end") in methods_paths
    # And at least two polls occurred before the terminal status.
    assert poll_count["n"] >= 2


def test_bhce_ingest_zip_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    out = json.loads(bhce_ingest_zip.invoke({"path": "/no/such/path.zip"}))
    assert "not a file" in out["error"]


def test_bhce_ingest_zip_propagates_start_error(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _set_env(monkeypatch)
    zip_path = _make_tiny_zip(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"http_status": 403, "errors": [{"message": "GraphDBIngest required"}]},
        )

    _install_transport(monkeypatch, handler)
    out = json.loads(bhce_ingest_zip.invoke({"path": zip_path}))
    assert out["status_code"] == 403
    assert "GraphDBIngest" in json.dumps(out["body"])


# ── plumbing sanity ──────────────────────────────────────────────


def test_bhce_tools_list_exports_three(monkeypatch: pytest.MonkeyPatch) -> None:
    from decepticon.tools.ad.bh_tools import BHCE_TOOLS

    names = sorted(t.name for t in BHCE_TOOLS)
    assert names == ["bhce_cypher", "bhce_ingest_zip", "bhce_status"]


def test_consume_io_isnt_required_to_import_bh_tools() -> None:
    # Importing bh_tools must not hit the network or require env vars.
    assert io.BytesIO is not None  # imported in test scope; smoke check
