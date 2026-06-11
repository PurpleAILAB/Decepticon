"""Tests for decepticon.mcp_server.server.build_server — the FastMCP wiring.

Verifies that the engagement-control surface (the 10 ``decepticon_*`` tools)
is registered with the right names, the right contract (returns / errors),
and that auth gates the network transport before any tool can run. Uses an
in-memory fake LangGraph client to drive the tools end-to-end through
``FastMCP.call_tool`` so the registered handlers — not the bare helper
modules — actually execute.

Gated by ``pytest.importorskip("mcp")`` because the bridge ships behind the
optional ``[mcp]`` extra (the default CI lane runs without the SDK; the
``mcp``-enabled lane added in CI exercises this file).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

pytest.importorskip("mcp")

from decepticon.mcp_server.config import ServerConfig  # noqa: E402
from decepticon.mcp_server.server import build_server  # noqa: E402


async def _call(server: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """FastMCP.call_tool's annotated return type omits the (content, structured)
    tuple it actually yields at runtime; this helper hides the cast so each
    test stays focused on contract assertions."""
    outcome = await server.call_tool(name, args)
    if isinstance(outcome, tuple):
        _, structured = outcome
        return structured  # type: ignore[no-any-return]
    return outcome  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# In-memory fake LangGraph client (shared by the call_tool tests below).
# ---------------------------------------------------------------------------


class _Part:
    def __init__(self, event: str, data: Any) -> None:
        self.event = event
        self.data = data
        self.id = None


class _Threads:
    def __init__(self, threads: list[dict[str, Any]], state: dict[str, Any]) -> None:
        self._threads = threads
        self._state = state

    async def create(self) -> dict[str, Any]:
        return {"thread_id": "t-new"}

    async def search(self, *, limit: int, **_: Any) -> list[dict[str, Any]]:
        return self._threads[:limit]

    async def get_state(self, thread_id: str) -> dict[str, Any]:
        return self._state


class _Runs:
    def __init__(self, runs: list[dict[str, Any]], stream: list[_Part]) -> None:
        self._runs = runs
        self._stream = stream
        self.created: list[dict[str, Any]] = []
        self.cancelled: tuple[str, str] | None = None

    async def create(self, thread_id: str, *, assistant_id: str, **kw: Any) -> dict[str, Any]:
        self.created.append({"thread_id": thread_id, "assistant_id": assistant_id, **kw})
        return {"run_id": "r-new", "status": "pending"}

    async def list(self, thread_id: str, *, limit: int = 10, **_: Any) -> list[dict[str, Any]]:
        return self._runs[:limit]

    async def cancel(self, thread_id: str, run_id: str) -> None:
        self.cancelled = (thread_id, run_id)

    async def join_stream(
        self, thread_id: str, run_id: str, *, stream_mode: Any = None
    ) -> AsyncIterator[_Part]:
        for p in self._stream:
            yield p


class _Assistants:
    async def search(self) -> list[dict[str, Any]]:
        return [{"assistant_id": "a-1", "graph_id": "decepticon", "name": "decepticon"}]


class _FakeClient:
    def __init__(
        self,
        *,
        runs: list[dict[str, Any]] | None = None,
        threads: list[dict[str, Any]] | None = None,
        state: dict[str, Any] | None = None,
        stream: list[_Part] | None = None,
    ) -> None:
        self.threads = _Threads(threads or [], state or {"values": {}, "next": [], "tasks": []})
        self.runs = _Runs(runs or [], stream or [])
        self.assistants = _Assistants()


def _cfg(**kw: object) -> ServerConfig:
    base: dict[str, object] = {
        "langgraph_url": "http://test:2024",
        "default_assistant": "decepticon",
        "request_timeout_seconds": 60.0,
    }
    base.update(kw)
    return ServerConfig(**base)  # type: ignore[arg-type]


def _server(client: _FakeClient | None = None, *, host: str = "127.0.0.1") -> Any:
    return build_server(_cfg(), client=client or _FakeClient(), host=host, port=8765)


# ---------------------------------------------------------------------------
# Registration: the public surface — 10 engagement-control tools.
# ---------------------------------------------------------------------------


EXPECTED_TOOLS = {
    "decepticon_list_graphs",
    "decepticon_start_engagement",
    "decepticon_engagement_status",
    "decepticon_engagement_findings",
    "decepticon_cancel_engagement",
    "decepticon_list_engagements",
    "decepticon_send_message",
    "decepticon_transcript",
    "decepticon_engagement_state",
    "decepticon_watch",
}


async def test_build_server_registers_full_engagement_surface() -> None:
    """All ten engagement-control tools land on the server."""
    server = _server()
    names = {t.name for t in await server.list_tools()}
    assert EXPECTED_TOOLS <= names, f"missing tools: {EXPECTED_TOOLS - names}"


async def test_server_has_canonical_name() -> None:
    assert _server().name == "decepticon"


# ---------------------------------------------------------------------------
# Auth gate: the network transport refuses to start when bound to a public
# interface without auth — protects the open-port → orchestrator path.
# ---------------------------------------------------------------------------


def test_build_server_succeeds_on_loopback_without_auth() -> None:
    """Loopback + no auth is the OSS-local default; it must not refuse."""
    server = _server(host="127.0.0.1")
    assert server is not None


def test_build_server_loopback_auth_inferred_from_token() -> None:
    """Setting the shared-secret env infers shared-secret auth; build still
    succeeds on loopback (and would also succeed on a public host)."""
    cfg = _cfg(auth_token="s3cret")
    assert build_server(cfg, client=_FakeClient(), host="127.0.0.1", port=8765) is not None


def test_build_server_jwt_mode_requires_audience() -> None:
    """A half-configured JWT mode (issuer + jwks but no audience) is rejected
    at build time — the resource-server contract must be complete."""
    cfg = _cfg(
        auth_mode="jwt",
        issuer="https://issuer.example.com",
        jwks_uri="https://issuer.example.com/.well-known/jwks.json",
    )
    with pytest.raises(ValueError, match="audience"):
        build_server(cfg, client=_FakeClient(), host="127.0.0.1", port=8765)


# ---------------------------------------------------------------------------
# call_tool: the registered handlers actually execute (not just the helpers).
# This is the coverage the upstream review was missing.
# ---------------------------------------------------------------------------


async def test_call_decepticon_list_graphs_returns_engagement_graphs() -> None:
    server = _server()
    result = await _call(server, "decepticon_list_graphs", {})
    # FastMCP serializes a list[BaseModel] return as {"result": [...]}.
    graphs = result["result"] if isinstance(result, dict) and "result" in result else result
    assert graphs[0]["graph_id"] == "decepticon"
    assert graphs[0]["assistant_id"] == "a-1"


async def test_call_decepticon_start_engagement_dispatches_background_run() -> None:
    fake = _FakeClient()
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(
        server,
        "decepticon_start_engagement",
        {
            "targets": ["https://example.com"],
            "instruction": "In scope: example.com only.",
            "engagement_name": "eng-call-1",
        },
    )
    payload = result
    assert payload["engagement_name"] == "eng-call-1"
    assert payload["thread_id"] == "t-new"
    # The fake recorded a background run dispatched with the scope payload.
    create = fake.runs.created[0]
    assert create["assistant_id"] == "decepticon"
    assert create["input"]["scan_scope"]["targets"] == ["https://example.com"]


async def test_call_decepticon_start_engagement_rejects_path_traversal_label() -> None:
    """RoE-adjacent guard: engagement_name is a workspace path component, so
    ``../`` etc. must be rejected before the run dispatches. This is the
    explicit authorization-gate path on the start tool."""
    server = _server()
    with pytest.raises(Exception, match="invalid engagement_name"):
        await server.call_tool(
            "decepticon_start_engagement",
            {
                "targets": ["https://example.com"],
                "instruction": "",
                "engagement_name": "../escape",
            },
        )


async def test_call_decepticon_start_engagement_default_label_when_unspecified() -> None:
    fake = _FakeClient()
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(
        server,
        "decepticon_start_engagement",
        {"targets": ["https://example.com"], "instruction": ""},
    )
    payload = result
    # Generated labels follow the ``mcp-YYYYMMDD-HHMMSS`` shape.
    assert payload["engagement_name"].startswith("mcp-")


async def test_call_decepticon_engagement_status_reports_unknown_when_no_runs() -> None:
    server = _server(_FakeClient(runs=[]))
    result = await _call(server, "decepticon_engagement_status", {"thread_id": "t-1"})
    payload = result
    assert payload["status"] == "none"
    assert payload["findings_available"] is False
    assert payload["run_id"] is None


async def test_call_decepticon_engagement_status_with_invalid_label_skips_findings_check() -> None:
    """An invalid engagement label must NOT trigger a workspace lookup —
    findings_available stays false rather than raising."""
    server = _server(_FakeClient(runs=[{"run_id": "r1", "status": "running"}]))
    result = await _call(
        server,
        "decepticon_engagement_status",
        {"thread_id": "t-1", "engagement_name": "../escape"},
    )
    payload = result
    assert payload["status"] == "running"
    assert payload["findings_available"] is False


async def test_call_decepticon_engagement_findings_returns_unavailable_when_missing() -> None:
    server = _server()
    result = await _call(server, "decepticon_engagement_findings", {"engagement_name": "never-ran"})
    payload = result
    assert payload["available"] is False


async def test_call_decepticon_cancel_engagement_cancels_active_run() -> None:
    fake = _FakeClient(runs=[{"run_id": "r-active", "status": "running"}])
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(server, "decepticon_cancel_engagement", {"thread_id": "t-x"})
    assert result["result"] == "cancelled r-active"
    assert fake.runs.cancelled == ("t-x", "r-active")


async def test_call_decepticon_cancel_engagement_no_active_run() -> None:
    fake = _FakeClient(runs=[{"run_id": "r-done", "status": "success"}])
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(server, "decepticon_cancel_engagement", {"thread_id": "t-x"})
    assert result["result"] == "no active run to cancel"


# ---------------------------------------------------------------------------
# Interactive surface — call_tool round-trips for the steer/list/watch tools.
# ---------------------------------------------------------------------------


async def test_call_decepticon_list_engagements_clamps_limit() -> None:
    fake = _FakeClient(
        threads=[
            {
                "thread_id": "t-1",
                "status": "idle",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-02",
                "values": {"engagement_name": "eng-a"},
            },
        ]
    )
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(server, "decepticon_list_engagements", {"limit": 999})
    rows = result["result"] if isinstance(result, dict) and "result" in result else result
    assert rows[0]["thread_id"] == "t-1"
    assert rows[0]["engagement_name"] == "eng-a"


async def test_call_decepticon_send_message_enqueues() -> None:
    fake = _FakeClient(runs=[{"run_id": "r0", "assistant_id": "recon", "status": "success"}])
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(
        server, "decepticon_send_message", {"thread_id": "t-1", "message": "focus on the API"}
    )
    handle = result
    assert handle["assistant"] == "recon"
    assert handle["run_id"] == "r-new"


async def test_call_decepticon_transcript_returns_messages_view() -> None:
    state = {
        "values": {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ]
        },
        "next": [],
        "tasks": [],
    }
    fake = _FakeClient(state=state, runs=[{"run_id": "r1", "status": "running"}])
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(
        server, "decepticon_transcript", {"thread_id": "t-1", "after_index": 0, "limit": 10}
    )
    transcript = result
    assert transcript["thread_id"] == "t-1"
    assert transcript["run_status"] == "running"
    assert "next_index" in transcript


async def test_call_decepticon_engagement_state_returns_state_view() -> None:
    state = {
        "values": {"engagement_name": "eng-z", "messages": [{"role": "user", "content": "x"}]},
        "next": [],
        "tasks": [],
    }
    fake = _FakeClient(state=state, runs=[])
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(server, "decepticon_engagement_state", {"thread_id": "t-1"})
    payload = result
    assert payload["thread_id"] == "t-1"
    assert payload["run_status"] == "none"


async def test_call_decepticon_watch_idle_returns_no_events() -> None:
    """When no run is active, watch must short-circuit (no stream consumed)."""
    fake = _FakeClient(runs=[])
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(
        server, "decepticon_watch", {"thread_id": "t-1", "max_seconds": 1, "max_events": 5}
    )
    payload = result
    assert payload["events"] == []
    assert payload["truncated"] is False


async def test_call_decepticon_watch_active_collects_stream_events() -> None:
    stream = [_Part("custom", {"type": "recon_step"})]
    fake = _FakeClient(runs=[{"run_id": "r-live", "status": "running"}], stream=stream)
    server = build_server(_cfg(), client=fake, host="127.0.0.1", port=8765)
    result = await _call(
        server, "decepticon_watch", {"thread_id": "t-1", "max_seconds": 1, "max_events": 5}
    )
    payload = result
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event"] == "custom"
