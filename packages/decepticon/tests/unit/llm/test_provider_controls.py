from __future__ import annotations

import pytest

from decepticon.llm.factory import _resolve_disable_streaming, _resolve_extra_headers


def test_extra_headers_accepts_string_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECEPTICON_LLM_EXTRA_HEADERS", '{"HTTP-Referer":"https://example.test"}')

    assert _resolve_extra_headers() == {"HTTP-Referer": "https://example.test"}


def test_extra_headers_rejects_malformed_or_protected_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECEPTICON_LLM_EXTRA_HEADERS", "[]")
    with pytest.raises(ValueError, match="JSON object"):
        _resolve_extra_headers()

    monkeypatch.setenv("DECEPTICON_LLM_EXTRA_HEADERS", '{"Authorization":"secret"}')
    with pytest.raises(ValueError, match="cannot override Authorization"):
        _resolve_extra_headers()


def test_disable_streaming_requires_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECEPTICON_LLM_DISABLE_STREAMING", "true")
    assert _resolve_disable_streaming() is True

    monkeypatch.setenv("DECEPTICON_LLM_DISABLE_STREAMING", "maybe")
    with pytest.raises(ValueError, match="must be a boolean"):
        _resolve_disable_streaming()
