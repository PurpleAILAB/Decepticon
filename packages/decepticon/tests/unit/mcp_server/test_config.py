"""Tests for decepticon.mcp_server.config (env-driven settings)."""

from __future__ import annotations

import pytest

from decepticon.mcp_server.config import (
    ENV_API_URL,
    ENV_ASSISTANT,
    ENV_AUDIENCE,
    ENV_AUTH,
    ENV_ISSUER,
    ENV_JWKS_URI,
    ENV_REQUIRED_SCOPES,
    ENV_TIMEOUT,
    ENV_TOKEN,
    load_config,
)


def test_load_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (ENV_API_URL, ENV_ASSISTANT, ENV_TIMEOUT):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.langgraph_url == "http://localhost:2024"
    assert cfg.default_assistant == "decepticon"
    assert cfg.request_timeout_seconds == 60.0


def test_load_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_API_URL, "http://example:9999")
    monkeypatch.setenv(ENV_ASSISTANT, "recon")
    monkeypatch.setenv(ENV_TIMEOUT, "12.5")
    cfg = load_config()
    assert cfg.langgraph_url == "http://example:9999"
    assert cfg.default_assistant == "recon"
    assert cfg.request_timeout_seconds == 12.5


def test_load_config_invalid_timeout_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_TIMEOUT, "not-a-number")
    assert load_config().request_timeout_seconds == 60.0


def test_load_config_nonpositive_timeout_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_TIMEOUT, "0")
    assert load_config().request_timeout_seconds == 60.0


def test_load_config_auth_unset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (ENV_AUTH, ENV_TOKEN, ENV_ISSUER, ENV_AUDIENCE, ENV_JWKS_URI, ENV_REQUIRED_SCOPES):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.auth_mode is None
    assert cfg.auth_token is None
    assert cfg.issuer is None
    assert cfg.required_scopes == ()


def test_load_config_reads_jwt_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_AUTH, "jwt")
    monkeypatch.setenv(ENV_ISSUER, "https://issuer/")
    monkeypatch.setenv(ENV_AUDIENCE, "decepticon-mcp")
    monkeypatch.setenv(ENV_JWKS_URI, "https://issuer/jwks")
    monkeypatch.setenv(ENV_REQUIRED_SCOPES, "engage, read  write")
    cfg = load_config()
    assert cfg.auth_mode == "jwt"
    assert cfg.issuer == "https://issuer/"
    assert cfg.audience == "decepticon-mcp"
    assert cfg.jwks_uri == "https://issuer/jwks"
    assert cfg.required_scopes == ("engage", "read", "write")


def test_load_config_reads_shared_secret_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_AUTH, raising=False)
    monkeypatch.setenv(ENV_TOKEN, "hunter2")
    assert load_config().auth_token == "hunter2"


def test_load_config_invalid_auth_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_AUTH, "totally-bogus")
    with pytest.raises(ValueError, match="must be one of"):
        load_config()
