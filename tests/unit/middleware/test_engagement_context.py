"""Tests for EngagementContextMiddleware — engagement and benchmark inject paths."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import SystemMessage

from decepticon.middleware.engagement_context import (
    EngagementContextMiddleware,
    _benchmark_mode_active,
)


class _FakeRequest:
    """Minimal duck-typed stand-in for the AgentMiddleware request object."""

    def __init__(
        self,
        state: dict[str, Any] | None = None,
        system_message: SystemMessage | None = None,
    ) -> None:
        self.state = state or {}
        self.system_message = system_message

    def override(self, system_message: SystemMessage) -> "_FakeRequest":
        return _FakeRequest(state=self.state, system_message=system_message)


def _flatten(message: SystemMessage | None) -> str:
    """Return the concatenated text of a SystemMessage regardless of content shape."""
    if message is None:
        return ""
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


@pytest.fixture
def middleware() -> EngagementContextMiddleware:
    return EngagementContextMiddleware()


@pytest.fixture(autouse=True)
def _clear_benchmark_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default each test to BENCHMARK_MODE unset; tests opt-in via monkeypatch.setenv."""
    monkeypatch.delenv("BENCHMARK_MODE", raising=False)


# ── env-var helper ─────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "anything"])
def test_benchmark_mode_active_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("BENCHMARK_MODE", value)
    assert _benchmark_mode_active() is True


@pytest.mark.parametrize("value", ["", "0", "false", "FALSE", "no", "off", "  "])
def test_benchmark_mode_active_falsy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("BENCHMARK_MODE", value)
    assert _benchmark_mode_active() is False


def test_benchmark_mode_active_unset() -> None:
    # autouse fixture deletes the env; must be False.
    assert _benchmark_mode_active() is False


# ── inject paths ───────────────────────────────────────────────────────


def test_no_injection_returns_request_unchanged(
    middleware: EngagementContextMiddleware,
) -> None:
    req = _FakeRequest(state={})
    result = middleware._inject(req)
    assert result is req
    assert result.system_message is None


def test_engagement_only_injection(middleware: EngagementContextMiddleware) -> None:
    req = _FakeRequest(
        state={"engagement_name": "blue-falcon", "workspace_path": "/workspace"},
    )
    result = middleware._inject(req)

    assert result is not req  # override produced a fresh request
    text = _flatten(result.system_message)
    assert "Workspace slug: blue-falcon" in text
    assert "Workspace root: /workspace" in text
    assert "BENCHMARK MODE" not in text  # benchmark section absent


def test_benchmark_mode_env_off_does_not_inject_challenge_context(
    middleware: EngagementContextMiddleware,
) -> None:
    """Even with full challenge state, no inject when BENCHMARK_MODE is unset."""
    req = _FakeRequest(
        state={
            "target_url": "http://host.docker.internal:8080",
            "vulnerability_tags": ["sqli"],
            "flag_format": "FLAG{<64-char-hex>}",
            "mission_brief": "Test challenge",
        },
    )
    result = middleware._inject(req)

    # No engagement_name and benchmark off → return original request.
    assert result is req


def test_benchmark_mode_env_on_injects_rules_override(
    monkeypatch: pytest.MonkeyPatch,
    middleware: EngagementContextMiddleware,
) -> None:
    """BENCHMARK_MODE=1 with empty state still injects the rule-suspension addendum."""
    monkeypatch.setenv("BENCHMARK_MODE", "1")
    req = _FakeRequest(state={})
    result = middleware._inject(req)

    text = _flatten(result.system_message)
    assert "[BENCHMARK MODE — engaged]" in text
    assert "Rule 8 (Startup Required)" in text
    assert "Rule 9 (Final Report)" in text
    assert "RECON objective" in text


def test_benchmark_mode_full_context(
    monkeypatch: pytest.MonkeyPatch,
    middleware: EngagementContextMiddleware,
) -> None:
    monkeypatch.setenv("BENCHMARK_MODE", "1")
    req = _FakeRequest(
        state={
            "engagement_name": "benchmark-XBEN-001-24",
            "workspace_path": "/workspace/benchmark-XBEN-001-24",
            "target_url": "http://host.docker.internal:33001",
            "target_extra_ports": {},
            "vulnerability_tags": ["sqli", "auth-bypass"],
            "flag_format": "FLAG{<64-char-hex>}",
            "mission_brief": "Login Form SQLi — bypass authentication",
        },
    )
    result = middleware._inject(req)

    text = _flatten(result.system_message)
    # engagement section
    assert "Workspace slug: benchmark-XBEN-001-24" in text
    # benchmark section
    assert "[BENCHMARK MODE — engaged]" in text
    assert "## CTF Benchmark Challenge" in text
    assert "**Target URL:** http://host.docker.internal:33001" in text
    assert "Attack ONLY this URL" in text
    assert "**Vulnerability tags:** sqli, auth-bypass" in text
    assert "**Flag format:** FLAG{<64-char-hex>}" in text
    assert "**Mission brief:** Login Form SQLi — bypass authentication" in text
    # engagement section comes before benchmark section
    assert text.index("Workspace slug:") < text.index("[BENCHMARK MODE")


def test_benchmark_extra_ports(
    monkeypatch: pytest.MonkeyPatch,
    middleware: EngagementContextMiddleware,
) -> None:
    monkeypatch.setenv("BENCHMARK_MODE", "1")
    req = _FakeRequest(
        state={
            "target_url": "http://host.docker.internal:33001",
            "target_extra_ports": {22: 2222, 3306: 33060},
            "vulnerability_tags": ["sqli"],
        },
    )
    result = middleware._inject(req)

    text = _flatten(result.system_message)
    assert "**Additional services:**" in text
    assert "**SSH:** host.docker.internal:2222 (internal port 22)" in text
    assert "**Port 3306:** host.docker.internal:33060" in text


def test_benchmark_extra_ports_empty_does_not_emit_section(
    monkeypatch: pytest.MonkeyPatch,
    middleware: EngagementContextMiddleware,
) -> None:
    monkeypatch.setenv("BENCHMARK_MODE", "1")
    req = _FakeRequest(
        state={
            "target_url": "http://host.docker.internal:33001",
            "target_extra_ports": {},
        },
    )
    result = middleware._inject(req)
    text = _flatten(result.system_message)
    assert "Additional services" not in text


def test_appended_to_existing_system_message(
    monkeypatch: pytest.MonkeyPatch,
    middleware: EngagementContextMiddleware,
) -> None:
    """When the request already has a system message, content_blocks are extended."""
    monkeypatch.setenv("BENCHMARK_MODE", "1")
    req = _FakeRequest(
        state={"engagement_name": "demo", "workspace_path": "/workspace"},
        system_message=SystemMessage(content="ORIGINAL_PROMPT_BODY"),
    )
    result = middleware._inject(req)
    text = _flatten(result.system_message)
    # original content is preserved; addendum is appended.
    assert "ORIGINAL_PROMPT_BODY" in text
    assert "Workspace slug: demo" in text
    assert "[BENCHMARK MODE — engaged]" in text
    assert text.index("ORIGINAL_PROMPT_BODY") < text.index("Workspace slug")


def test_benchmark_with_missing_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
    middleware: EngagementContextMiddleware,
) -> None:
    """Empty optional fields are silently skipped — only non-empty pieces appear."""
    monkeypatch.setenv("BENCHMARK_MODE", "1")
    req = _FakeRequest(state={"target_url": "http://x"})
    result = middleware._inject(req)
    text = _flatten(result.system_message)

    assert "**Target URL:** http://x" in text
    # No tags / flag_format / brief sections.
    assert "**Vulnerability tags:**" not in text
    assert "**Flag format:**" not in text
    assert "**Mission brief:**" not in text
