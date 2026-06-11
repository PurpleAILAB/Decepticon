"""Tests for the ``decepticon-mcp`` CLI entrypoint (decepticon.mcp_server.__main__).

The entrypoint is the only place where the auth gate translates into a process
exit — so an unauthenticated public bind must terminate before ``server.run()``
is reached. These tests exercise that path plus the CLI-flag → config overlay,
the install-hint path when the SDK is absent, and a clean stdio startup.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

pytest.importorskip("mcp")

from decepticon.mcp_server import __main__ as cli  # noqa: E402


class _FakeServer:
    """Captures the transport ``server.run()`` was invoked with."""

    def __init__(self) -> None:
        self.transport: str | None = None

    def run(self, *, transport: str) -> None:
        self.transport = transport


def test_main_refuses_unauth_public_bind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--transport streamable-http --host 0.0.0.0`` with no auth must exit 2."""
    monkeypatch.delenv("DECEPTICON_MCP_TOKEN", raising=False)
    monkeypatch.delenv("DECEPTICON_MCP_SERVER__AUTH", raising=False)
    rc = cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Refusing to start" in err
    assert "0.0.0.0" in err


def test_main_stdio_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdio is a local pipe — no auth needed. Build + ``run`` must be invoked."""
    captured = _FakeServer()
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: cli.ServerConfig(  # type: ignore[attr-defined]
            langgraph_url="http://localhost:2024",
            default_assistant="decepticon",
            request_timeout_seconds=60.0,
        ),
    )
    monkeypatch.setattr(
        "decepticon.mcp_server.server.build_server",
        lambda cfg, host, port: captured,
    )
    rc = cli.main(["--transport", "stdio"])
    assert rc == 0
    assert captured.transport == "stdio"


def test_main_loopback_streamable_http_starts_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loopback streamable-http stays auth-free (local dev shape)."""
    captured = _FakeServer()
    monkeypatch.delenv("DECEPTICON_MCP_TOKEN", raising=False)
    monkeypatch.setattr(
        "decepticon.mcp_server.server.build_server",
        lambda cfg, host, port: captured,
    )
    rc = cli.main(["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "8765"])
    assert rc == 0
    assert captured.transport == "streamable-http"


def test_main_shared_secret_env_unblocks_public_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting ``DECEPTICON_MCP_TOKEN`` infers shared-secret auth and the
    refuse-open-bind guard must allow startup."""
    captured = _FakeServer()
    monkeypatch.setenv("DECEPTICON_MCP_TOKEN", "secret-deadbeef")
    monkeypatch.setattr(
        "decepticon.mcp_server.server.build_server",
        lambda cfg, host, port: captured,
    )
    rc = cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"])
    assert rc == 0
    assert captured.transport == "streamable-http"


def test_main_misconfigured_auth_exits_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--auth jwt`` selected without issuer/audience must exit 2 with a
    one-line error — not a stack trace."""
    monkeypatch.delenv("DECEPTICON_MCP_TOKEN", raising=False)
    rc = cli.main(
        [
            "--transport",
            "stdio",
            "--auth",
            "jwt",
            "--issuer",
            "https://issuer.example.com",
            "--jwks-uri",
            "https://issuer.example.com/.well-known/jwks.json",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "decepticon-mcp:" in err
    assert "audience" in err


def test_main_install_hint_when_mcp_sdk_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the [mcp] extra is not installed, importing the auth module raises
    ImportError; the CLI must print the install hint and exit 2 rather than
    blow up with a traceback."""

    def _raise(name: str, package: Any = None) -> Any:
        raise ImportError("no module named mcp")

    monkeypatch.setitem(sys.modules, "decepticon.mcp_server.auth", None)
    monkeypatch.setitem(sys.modules, "decepticon.mcp_server.server", None)
    rc = cli.main(["--transport", "stdio"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "decepticon[mcp]" in err


def test_main_cli_overlays_apply_to_config() -> None:
    """``_apply_cli`` overlays selected CLI flags onto the env-derived config."""
    args = cli._build_parser().parse_args(
        [
            "--transport",
            "stdio",
            "--langgraph-url",
            "http://override:2024",
            "--auth",
            "shared-secret",
            "--issuer",
            "https://i.example",
            "--audience",
            "decepticon-mcp",
            "--jwks-uri",
            "https://i.example/jwks",
            "--auth-public-key",
            "/tmp/key.pem",
            "--resource-url",
            "https://r.example",
            "--required-scope",
            "engage",
            "--required-scope",
            "read",
        ]
    )
    cfg = cli._apply_cli(
        cli.ServerConfig(  # type: ignore[attr-defined]
            langgraph_url="http://default:2024",
            default_assistant="decepticon",
            request_timeout_seconds=60.0,
        ),
        args,
    )
    assert cfg.langgraph_url == "http://override:2024"
    assert cfg.auth_mode == "shared-secret"
    assert cfg.issuer == "https://i.example"
    assert cfg.audience == "decepticon-mcp"
    assert cfg.jwks_uri == "https://i.example/jwks"
    assert cfg.public_key == "/tmp/key.pem"
    assert cfg.resource_url == "https://r.example"
    assert cfg.required_scopes == ("engage", "read")


def test_main_empty_cli_returns_unmodified_config() -> None:
    """No flags → no overlay; the input ServerConfig is returned as-is."""
    args = cli._build_parser().parse_args(["--transport", "stdio"])
    base = cli.ServerConfig(  # type: ignore[attr-defined]
        langgraph_url="http://default:2024",
        default_assistant="decepticon",
        request_timeout_seconds=60.0,
    )
    assert cli._apply_cli(base, args) is base
