"""Environment-driven configuration for the engagement MCP server.

The bridge drives a *running* Decepticon LangGraph server. The default URL
matches ``decepticon.cli.scan``'s ``--langgraph-url`` default and the same
``DECEPTICON_API_URL`` env var, so the MCP server, the headless CLI, and the
web client all agree on where the platform lives.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: LangGraph platform URL the bridge connects to.
ENV_API_URL = "DECEPTICON_API_URL"
#: Default assistant/graph used when a tool call omits one.
ENV_ASSISTANT = "DECEPTICON_MCP_SERVER__ASSISTANT"
#: Per-request timeout (seconds) for LangGraph SDK calls.
ENV_TIMEOUT = "DECEPTICON_MCP_SERVER__REQUEST_TIMEOUT"

_DEFAULT_URL = "http://localhost:2024"
_DEFAULT_ASSISTANT = "decepticon"
_DEFAULT_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Resolved settings for the engagement MCP bridge."""

    langgraph_url: str
    default_assistant: str
    request_timeout_seconds: float


def _parse_timeout(raw: str | None) -> float:
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT
    return value if value > 0 else _DEFAULT_TIMEOUT


def load_config() -> ServerConfig:
    """Build a :class:`ServerConfig` from ``DECEPTICON_*`` environment variables."""
    return ServerConfig(
        langgraph_url=os.environ.get(ENV_API_URL) or _DEFAULT_URL,
        default_assistant=os.environ.get(ENV_ASSISTANT) or _DEFAULT_ASSISTANT,
        request_timeout_seconds=_parse_timeout(os.environ.get(ENV_TIMEOUT)),
    )
