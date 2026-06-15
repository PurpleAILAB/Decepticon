"""Unit tests for the browser-tier fallback executor."""

from __future__ import annotations

import pytest

from decepticon.sandbox_web import executor
from decepticon.sandbox_web.executor import run_browser_fallback
from decepticon.sandbox_web.validators import SMALL_BODY_THRESHOLD, Verdict


def test_playwright_absent_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor, "_render_with_playwright", lambda *a, **k: None)
    att, html = run_browser_fallback("https://example.com/x")
    assert att.verdict == Verdict.UNKNOWN.value
    assert html == ""
    assert att.error is not None
    assert "playwright not installed" in att.error
    assert att.phase == "fallback"


def test_render_success_validates_strong_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    html = "x" * (SMALL_BODY_THRESHOLD + 50) + "<article id='c'>hi</article>"
    monkeypatch.setattr(
        executor,
        "_render_with_playwright",
        lambda *a, **k: (html, "https://example.com/final"),
    )
    att, out = run_browser_fallback("https://example.com/x", success_selectors=["article#c"])
    assert att.verdict == Verdict.STRONG_OK.value
    assert att.url == "https://example.com/final"
    assert out == html
    assert att.body_size == len(html)


def test_render_challenge_is_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        executor,
        "_render_with_playwright",
        lambda *a, **k: ("Just a moment...", "https://example.com/x"),
    )
    att, _out = run_browser_fallback("https://example.com/x")
    assert att.verdict == Verdict.CHALLENGE.value


def test_browser_error_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object):
        raise executor._BrowserError("Timeout:nav")

    monkeypatch.setattr(executor, "_render_with_playwright", boom)
    att, html = run_browser_fallback("https://example.com/x")
    assert att.verdict == Verdict.UNKNOWN.value
    assert html == ""
    assert att.error == "Timeout:nav"
