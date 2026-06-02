"""Tests for ``decepticon.tools.mcp.client``.

These tests must never reach the real network and must never require
``langchain-mcp-adapters`` to be installed — both are simulated via
monkeypatching ``sys.modules``.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from typing import Any

import pytest

from decepticon.tools.mcp.client import (
    ENV_SERVERS,
    MCPServerConfig,
    load_mcp_tools,
    mcp_servers_configured,
    parse_mcp_servers_env,
)


@pytest.fixture(autouse=True)
def _propagate_mcp_logger():
    """Let ``caplog`` see records — the ``decepticon`` root sets
    ``propagate=False`` (see ``decepticon_core.utils.logging``).
    """
    # The "decepticon" root logger has ``propagate=False`` — records
    # never reach pytest's root-level caplog handler unless we flip it.
    root = logging.getLogger("decepticon")
    prev = root.propagate
    root.propagate = True
    try:
        yield
    finally:
        root.propagate = prev


# ---------------------------------------------------------------- parse


def test_parse_empty_returns_empty_tuple():
    assert parse_mcp_servers_env(None) == ()
    assert parse_mcp_servers_env("") == ()
    assert parse_mcp_servers_env("   ") == ()


def test_parse_two_servers_roundtrip():
    raw = json.dumps(
        {
            "kali": {"url": "http://localhost:8000/mcp", "transport": "streamable_http"},
            "hex": {"command": "uvx", "args": ["hexstrike"], "transport": "stdio"},
        }
    )
    parsed = parse_mcp_servers_env(raw)
    assert len(parsed) == 2
    by_name = {s.name: s for s in parsed}
    assert by_name["kali"].transport == "streamable_http"
    assert by_name["kali"].url == "http://localhost:8000/mcp"
    assert by_name["hex"].transport == "stdio"
    assert by_name["hex"].command == "uvx"
    assert by_name["hex"].args == ("hexstrike",)


def test_parse_default_transport_http_when_url_only():
    raw = json.dumps({"a": {"url": "http://x/mcp"}})
    (cfg,) = parse_mcp_servers_env(raw)
    assert cfg.transport == "streamable_http"


def test_parse_default_transport_stdio_when_command_present():
    raw = json.dumps({"a": {"command": "uvx", "args": ["foo"]}})
    (cfg,) = parse_mcp_servers_env(raw)
    assert cfg.transport == "stdio"


def test_parse_malformed_json_returns_empty_and_warns(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = parse_mcp_servers_env("{not valid json")
    assert result == ()
    assert any("malformed JSON" in rec.message for rec in caplog.records)


def test_parse_non_object_top_level_returns_empty(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = parse_mcp_servers_env(json.dumps(["not", "an", "object"]))
    assert result == ()
    assert any("must be a JSON object" in rec.message for rec in caplog.records)


def test_parse_unknown_transport_is_skipped(caplog: pytest.LogCaptureFixture):
    raw = json.dumps(
        {
            "good": {"url": "http://x/mcp", "transport": "streamable_http"},
            "bad": {"url": "http://y/mcp", "transport": "carrier-pigeon"},
        }
    )
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        parsed = parse_mcp_servers_env(raw)
    names = {s.name for s in parsed}
    assert names == {"good"}
    assert any("unknown transport" in rec.message for rec in caplog.records)


def test_parse_bad_entry_shape_is_skipped(caplog: pytest.LogCaptureFixture):
    raw = json.dumps({"weird": "not-an-object"})
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        parsed = parse_mcp_servers_env(raw)
    assert parsed == ()
    assert any("must be a JSON object" in rec.message for rec in caplog.records)


def test_to_client_kwargs_http_includes_url_and_headers():
    cfg = MCPServerConfig(
        name="kali",
        transport="streamable_http",
        url="http://x/mcp",
        headers={"Authorization": "Bearer t"},
    )
    kwargs = cfg.to_client_kwargs()
    assert kwargs == {
        "transport": "streamable_http",
        "url": "http://x/mcp",
        "headers": {"Authorization": "Bearer t"},
    }


def test_to_client_kwargs_stdio_includes_command_args():
    cfg = MCPServerConfig(
        name="hex", transport="stdio", command="uvx", args=("hexstrike", "--flag")
    )
    kwargs = cfg.to_client_kwargs()
    assert kwargs == {
        "transport": "stdio",
        "command": "uvx",
        "args": ["hexstrike", "--flag"],
    }


# ---------------------------------------------------------------- env probe


def test_mcp_servers_configured_false_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ENV_SERVERS, raising=False)
    assert mcp_servers_configured() is False


def test_mcp_servers_configured_true_when_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        ENV_SERVERS,
        json.dumps({"k": {"url": "http://x/mcp", "transport": "streamable_http"}}),
    )
    assert mcp_servers_configured() is True


# ---------------------------------------------------------------- load_mcp_tools


async def test_load_mcp_tools_no_servers_returns_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ENV_SERVERS, raising=False)
    assert await load_mcp_tools() == []


async def test_load_mcp_tools_malformed_env_returns_empty(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setenv(ENV_SERVERS, "{bogus")
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = await load_mcp_tools()
    assert result == []


async def test_load_mcp_tools_missing_package_is_graceful(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """If langchain_mcp_adapters can't be imported, return [] with a warning."""
    # Block both the package and the submodule. ``import x.y`` consults
    # ``sys.modules`` first and raises ImportError when the value is None.
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", None)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", None)
    servers = (MCPServerConfig(name="kali", transport="streamable_http", url="http://x/mcp"),)
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = await load_mcp_tools(servers)
    assert result == []
    assert any("langchain-mcp-adapters" in rec.message for rec in caplog.records)


async def test_load_mcp_tools_uses_mock_client_when_package_present(
    monkeypatch: pytest.MonkeyPatch,
):
    """Inject a fake ``langchain_mcp_adapters.client.MultiServerMCPClient``."""
    sentinel_tools = [object(), object()]
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, connections: dict[str, Any]):
            captured["connections"] = connections

        async def get_tools(self) -> list[Any]:
            return sentinel_tools

    fake_pkg = types.ModuleType("langchain_mcp_adapters")
    fake_client_mod = types.ModuleType("langchain_mcp_adapters.client")
    fake_client_mod.MultiServerMCPClient = FakeClient  # type: ignore[attr-defined]
    fake_pkg.client = fake_client_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", fake_pkg)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", fake_client_mod)

    servers = (
        MCPServerConfig(
            name="kali",
            transport="streamable_http",
            url="http://localhost:8000/mcp",
            headers={"X-Auth": "secret"},
        ),
    )
    result = await load_mcp_tools(servers)
    assert result == sentinel_tools
    assert captured["connections"] == {
        "kali": {
            "transport": "streamable_http",
            "url": "http://localhost:8000/mcp",
            "headers": {"X-Auth": "secret"},
        }
    }


async def test_load_mcp_tools_retries_transient_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A server whose get_tools() fails twice then succeeds is retried."""
    from decepticon.tools.mcp import client as mcp_client

    sentinel_tools = [object()]
    attempts: list[int] = []

    class FakeClient:
        def __init__(self, connections: dict[str, Any]):
            pass

        async def get_tools(self) -> list[Any]:
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return sentinel_tools

    fake_pkg = types.ModuleType("langchain_mcp_adapters")
    fake_client_mod = types.ModuleType("langchain_mcp_adapters.client")
    fake_client_mod.MultiServerMCPClient = FakeClient  # type: ignore[attr-defined]
    fake_pkg.client = fake_client_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", fake_pkg)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", fake_client_mod)

    sleeps: list[float] = []

    async def _no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(mcp_client, "_sleep", _no_sleep)

    servers = (MCPServerConfig(name="kali", transport="streamable_http", url="http://x/mcp"),)
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = await load_mcp_tools(servers)
    assert result == sentinel_tools
    assert len(attempts) == 3
    assert len(sleeps) == 2
    assert all(s > 0 for s in sleeps)


async def test_load_mcp_tools_skips_after_all_attempts_exhausted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A server that fails every retry is logged+skipped (current end-state)."""
    from decepticon.tools.mcp import client as mcp_client

    attempts: list[int] = []

    class FakeClient:
        def __init__(self, connections: dict[str, Any]):
            pass

        async def get_tools(self) -> list[Any]:
            attempts.append(1)
            raise ConnectionError("down")

    fake_pkg = types.ModuleType("langchain_mcp_adapters")
    fake_client_mod = types.ModuleType("langchain_mcp_adapters.client")
    fake_client_mod.MultiServerMCPClient = FakeClient  # type: ignore[attr-defined]
    fake_pkg.client = fake_client_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", fake_pkg)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", fake_client_mod)

    async def _no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(mcp_client, "_sleep", _no_sleep)

    servers = (MCPServerConfig(name="bad", transport="streamable_http", url="http://x/mcp"),)
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = await load_mcp_tools(servers)
    assert result == []
    assert len(attempts) >= 2
    assert any("unreachable" in rec.message for rec in caplog.records)


async def test_load_mcp_tools_one_bad_server_does_not_kill_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    good_tool = object()

    class FakeClient:
        def __init__(self, connections: dict[str, Any]):
            self._connections = connections

        async def get_tools(self) -> list[Any]:
            if "bad" in self._connections:
                raise ConnectionError("nope")
            return [good_tool]

    fake_pkg = types.ModuleType("langchain_mcp_adapters")
    fake_client_mod = types.ModuleType("langchain_mcp_adapters.client")
    fake_client_mod.MultiServerMCPClient = FakeClient  # type: ignore[attr-defined]
    fake_pkg.client = fake_client_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", fake_pkg)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", fake_client_mod)

    servers = (
        MCPServerConfig(name="bad", transport="streamable_http", url="http://x/mcp"),
        MCPServerConfig(name="ok", transport="streamable_http", url="http://y/mcp"),
    )
    with caplog.at_level(logging.WARNING, logger="decepticon.tools.mcp"):
        result = await load_mcp_tools(servers)
    assert result == [good_tool]
    assert any("unreachable" in rec.message for rec in caplog.records)
