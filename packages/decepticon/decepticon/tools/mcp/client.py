"""MCP tool-server client — opt-in, lazy, never fatal.

This module is the single bridge between Decepticon and external
Model Context Protocol (MCP) servers (e.g. a Kali MCP daemon,
HexStrike). It is deliberately additive and self-contained:

- Nothing here is imported at framework start-up.
- The heavy dependency (``langchain-mcp-adapters``) is imported
  *inside* :func:`load_mcp_tools`, wrapped in ``try/except
  ImportError`` so missing it merely disables MCP — agents keep
  working.
- A single misconfigured server logs+skips; it never kills the
  whole tool-load.

Configuration
-------------
Operators set ``DECEPTICON_MCP__SERVERS`` to a JSON object mapping
server-name -> per-server config::

    DECEPTICON_MCP__SERVERS='{
        "kali":    {"url": "http://localhost:8000/mcp",
                    "transport": "streamable_http"},
        "hex":     {"command": "uvx", "args": ["hexstrike"],
                    "transport": "stdio"}
    }'

The env-var naming matches the existing ``DECEPTICON_<SECTION>__<KEY>``
convention used by ``DECEPTICON_BUDGET__*``, ``DECEPTICON_RUNTIME__*``,
``DECEPTICON_LLM__*``.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from decepticon_core.utils.logging import get_logger

log = get_logger("tools.mcp")

#: Env var that carries the JSON server map. Empty / unset => MCP off.
ENV_SERVERS = "DECEPTICON_MCP__SERVERS"

#: Transports recognised by ``langchain-mcp-adapters``' MultiServerMCPClient.
Transport = Literal["streamable_http", "sse", "stdio"]

_VALID_TRANSPORTS: frozenset[str] = frozenset({"streamable_http", "sse", "stdio"})

#: Bounded retry policy for per-server MCP connect+get_tools. A transient
#: network hiccup must not permanently drop a server's tools, but we still
#: need a hard ceiling so a dead endpoint can't stall agent start-up.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0

#: Module-level sleep indirection so tests can patch it to a no-op without
#: monkey-patching ``asyncio.sleep`` globally.
_sleep = asyncio.sleep


@dataclass(frozen=True)
class MCPServerConfig:
    """Parsed configuration for a single MCP server.

    Mirrors the per-server kwargs accepted by
    ``langchain_mcp_adapters.client.MultiServerMCPClient``. Only fields
    relevant to the chosen ``transport`` are populated; the others
    stay at their dataclass defaults.

    Attributes:
        name: server identifier (the JSON map key).
        transport: ``streamable_http`` / ``sse`` (HTTP-style) or
            ``stdio`` (subprocess-style).
        url: target URL for HTTP transports.
        command: executable for stdio transport.
        args: argv tail for stdio transport.
        headers: optional HTTP headers (auth tokens, etc.).
    """

    name: str
    transport: Transport
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    headers: Mapping[str, str] = field(default_factory=dict)

    def to_client_kwargs(self) -> dict[str, Any]:
        """Render this config as the dict ``MultiServerMCPClient`` expects."""
        payload: dict[str, Any] = {"transport": self.transport}
        if self.transport == "stdio":
            if self.command is not None:
                payload["command"] = self.command
            if self.args:
                payload["args"] = list(self.args)
        else:
            if self.url is not None:
                payload["url"] = self.url
            if self.headers:
                payload["headers"] = dict(self.headers)
        return payload


def _default_transport(entry: Mapping[str, Any]) -> Transport:
    """Pick a sensible transport when the user omitted one.

    Rules: ``command`` present => ``stdio``; otherwise ``streamable_http``
    (the modern HTTP transport — operators on legacy SSE servers must
    set ``transport`` explicitly).
    """
    if "command" in entry:
        return "stdio"
    return "streamable_http"


def _parse_one(name: str, entry: Any) -> MCPServerConfig | None:
    """Parse a single server entry. Returns ``None`` on invalid input."""
    if not isinstance(entry, Mapping):
        log.warning(
            "ignoring MCP server %r: entry must be a JSON object, got %s",
            name,
            type(entry).__name__,
        )
        return None

    transport_raw = entry.get("transport") or _default_transport(entry)
    if transport_raw not in _VALID_TRANSPORTS:
        log.warning(
            "ignoring MCP server %r: unknown transport %r (expected one of %s)",
            name,
            transport_raw,
            sorted(_VALID_TRANSPORTS),
        )
        return None
    transport: Transport = transport_raw  # type: narrow

    args_raw = entry.get("args") or ()
    if not isinstance(args_raw, (list, tuple)):
        log.warning("ignoring MCP server %r: 'args' must be a list", name)
        return None

    headers_raw = entry.get("headers") or {}
    if not isinstance(headers_raw, Mapping):
        log.warning("ignoring MCP server %r: 'headers' must be an object", name)
        return None

    return MCPServerConfig(
        name=name,
        transport=transport,
        url=entry.get("url"),
        command=entry.get("command"),
        args=tuple(str(a) for a in args_raw),
        headers={str(k): str(v) for k, v in headers_raw.items()},
    )


def parse_mcp_servers_env(raw: str | None) -> tuple[MCPServerConfig, ...]:
    """Parse the JSON value of ``DECEPTICON_MCP__SERVERS``.

    Empty / whitespace / unset input returns ``()``. Malformed JSON
    logs a warning and also returns ``()`` (never raises — a busted
    env var must not crash the agent process).
    """
    if not raw or not raw.strip():
        return ()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning(
            "ignoring %s: malformed JSON (%s); set it to a JSON object "
            "mapping server-name -> config",
            ENV_SERVERS,
            exc,
        )
        return ()
    if not isinstance(loaded, Mapping):
        log.warning(
            "ignoring %s: top-level value must be a JSON object, got %s",
            ENV_SERVERS,
            type(loaded).__name__,
        )
        return ()

    parsed: list[MCPServerConfig] = []
    for name, entry in loaded.items():
        cfg = _parse_one(str(name), entry)
        if cfg is not None:
            parsed.append(cfg)
    return tuple(parsed)


def _read_env_servers() -> tuple[MCPServerConfig, ...]:
    return parse_mcp_servers_env(os.environ.get(ENV_SERVERS))


def mcp_servers_configured() -> bool:
    """``True`` iff at least one MCP server is configured via env."""
    return bool(_read_env_servers())


async def load_mcp_tools(
    config: tuple[MCPServerConfig, ...] | None = None,
) -> list[Any]:
    """Connect to every configured MCP server and return their tools.

    If ``config`` is omitted, the env var is parsed. Empty config =>
    ``[]`` with no work done. The optional ``langchain-mcp-adapters``
    dependency is imported lazily here; absence is downgraded to a
    one-line warning + empty list so agents stay usable.

    A failure connecting to *one* server is logged and skipped — other
    servers still contribute their tools.
    """
    servers = config if config is not None else _read_env_servers()
    if not servers:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        log.warning(
            "%s is set but the optional 'langchain-mcp-adapters' package "
            "is not installed; install it (e.g. `pip install "
            "langchain-mcp-adapters`) to enable MCP tools",
            ENV_SERVERS,
        )
        return []

    # MultiServerMCPClient accepts the whole connection dict up-front,
    # but per-server connection failures inside get_tools() would tank
    # the entire load. We therefore probe servers one-by-one so a
    # single bad endpoint doesn't kill the rest.
    collected: list[Any] = []
    for srv in servers:
        connections = {srv.name: srv.to_client_kwargs()}
        tools: list[Any] | None = None
        last_exc: BaseException | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                client = MultiServerMCPClient(connections)
                tools = await client.get_tools()
                break
            except Exception as exc:  # noqa: BLE001 — third-party I/O
                last_exc = exc
                if attempt < _MAX_ATTEMPTS:
                    delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    log.info(
                        "MCP server %r attempt %d/%d failed (%s: %s); retrying in %.1fs",
                        srv.name,
                        attempt,
                        _MAX_ATTEMPTS,
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    await _sleep(delay)
        if tools is None:
            log.warning(
                "MCP server %r unreachable, skipping (%s: %s)",
                srv.name,
                type(last_exc).__name__ if last_exc is not None else "Error",
                last_exc,
            )
            continue
        log.info("loaded %d tool(s) from MCP server %r", len(tools), srv.name)
        collected.extend(tools)
    return collected
