"""Tests for decepticon.mcp_server.config (env-driven settings)."""

from __future__ import annotations

import pytest

from decepticon.mcp_server.config import (
    ENV_API_URL,
    ENV_ASSISTANT,
    ENV_TIMEOUT,
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
