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
#: Auth mode override ("none" | "shared-secret" | "jwt"); unset → inferred.
ENV_AUTH = "DECEPTICON_MCP_SERVER__AUTH"
#: Shared-secret bearer token (presence infers shared-secret mode).
ENV_TOKEN = "DECEPTICON_MCP_TOKEN"
#: JWT issuer (``iss``) the bearer token must carry.
ENV_ISSUER = "DECEPTICON_MCP_SERVER__ISSUER"
#: JWT audience (``aud``) the bearer token must carry.
ENV_AUDIENCE = "DECEPTICON_MCP_SERVER__AUDIENCE"
#: JWKS endpoint used to fetch the JWT signing key.
ENV_JWKS_URI = "DECEPTICON_MCP_SERVER__JWKS_URI"
#: Static JWT public key — a filesystem path or inline PEM.
ENV_PUBLIC_KEY = "DECEPTICON_MCP_SERVER__PUBLIC_KEY"
#: This server's public URL (OAuth resource identifier); defaults to host:port.
ENV_RESOURCE_URL = "DECEPTICON_MCP_SERVER__RESOURCE_URL"
#: Comma/space-delimited scopes a JWT must carry to be authorized.
ENV_REQUIRED_SCOPES = "DECEPTICON_MCP_SERVER__REQUIRED_SCOPES"

_DEFAULT_URL = "http://localhost:2024"
_DEFAULT_ASSISTANT = "decepticon"
_DEFAULT_TIMEOUT = 60.0
_AUTH_MODES = frozenset({"none", "shared-secret", "jwt"})


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Resolved settings for the engagement MCP bridge."""

    langgraph_url: str
    default_assistant: str
    request_timeout_seconds: float
    auth_mode: str | None = None
    auth_token: str | None = None
    issuer: str | None = None
    audience: str | None = None
    jwks_uri: str | None = None
    public_key: str | None = None
    resource_url: str | None = None
    required_scopes: tuple[str, ...] = ()


def _parse_timeout(raw: str | None) -> float:
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT
    return value if value > 0 else _DEFAULT_TIMEOUT


def _parse_scopes(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(s for s in raw.replace(",", " ").split() if s)


def _parse_auth_mode(raw: str | None) -> str | None:
    if not raw:
        return None
    mode = raw.strip().lower()
    if mode not in _AUTH_MODES:
        raise ValueError(f"{ENV_AUTH} must be one of {sorted(_AUTH_MODES)}, got {raw!r}")
    return mode


def load_config() -> ServerConfig:
    """Build a :class:`ServerConfig` from ``DECEPTICON_*`` environment variables."""
    return ServerConfig(
        langgraph_url=os.environ.get(ENV_API_URL) or _DEFAULT_URL,
        default_assistant=os.environ.get(ENV_ASSISTANT) or _DEFAULT_ASSISTANT,
        request_timeout_seconds=_parse_timeout(os.environ.get(ENV_TIMEOUT)),
        auth_mode=_parse_auth_mode(os.environ.get(ENV_AUTH)),
        auth_token=os.environ.get(ENV_TOKEN) or None,
        issuer=os.environ.get(ENV_ISSUER) or None,
        audience=os.environ.get(ENV_AUDIENCE) or None,
        jwks_uri=os.environ.get(ENV_JWKS_URI) or None,
        public_key=os.environ.get(ENV_PUBLIC_KEY) or None,
        resource_url=os.environ.get(ENV_RESOURCE_URL) or None,
        required_scopes=_parse_scopes(os.environ.get(ENV_REQUIRED_SCOPES)),
    )
