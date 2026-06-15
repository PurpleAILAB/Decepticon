"""Unit tests for the fetch chain — grid logic + RoE per-hop scope gate.

No real egress: ``_curl_probe`` is monkeypatched to return canned responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest

from decepticon.sandbox_web import fetch_chain
from decepticon.sandbox_web.fetch_chain import fetch
from decepticon.sandbox_web.validators import SMALL_BODY_THRESHOLD, Verdict


@dataclass
class _FakeResp:
    status_code: int = 200
    text: str = ""
    url: str = "https://example.com/"
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


_OK_BODY = "x" * (SMALL_BODY_THRESHOLD + 100)
_CHALLENGE_BODY = "Just a moment..."


def _patch_probe(monkeypatch: pytest.MonkeyPatch, fn) -> None:
    monkeypatch.setattr(fetch_chain, "_curl_probe", fn)
    # Kill jitter sleeps so the grid runs fast.
    monkeypatch.setattr(fetch_chain, "_jitter", lambda: None)


def test_probe_success_returns_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(url: str, **_kw: object):
        return _FakeResp(text=_OK_BODY, url=url), None

    _patch_probe(monkeypatch, probe)
    r = fetch("https://example.com/page", enable_playwright=False)
    assert r.ok
    assert r.verdict == Verdict.WEAK_OK.value
    assert len(r.trace) == 1
    assert r.trace[0].phase == "probe"


def test_input_url_out_of_scope_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    def probe(url: str, **_kw: object):
        called["n"] += 1
        return _FakeResp(text=_OK_BODY), None

    _patch_probe(monkeypatch, probe)
    r = fetch("https://evil.example.org/x", scope_check=lambda _u: False, enable_playwright=False)
    assert not r.ok
    assert r.verdict == Verdict.BLOCKED.value
    assert "scope" in r.summary
    assert called["n"] == 0  # never hit the network
    assert r.trace[0].reasons == ["out_of_roe_scope"]


def test_challenge_then_grid_success(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"calls": 0}

    def probe(url: str, *, impersonate: str, referer: str, timeout: int = 20):
        state["calls"] += 1
        # First call (probe) → challenge; later grid call → success.
        if state["calls"] == 1:
            return _FakeResp(text=_CHALLENGE_BODY, cookies={"_abck": "x"}), None
        return _FakeResp(text=_OK_BODY, url=url), None

    _patch_probe(monkeypatch, probe)
    r = fetch("https://www.example.com/p", enable_playwright=False)
    assert r.ok
    assert state["calls"] >= 2
    assert any(a.phase == "grid" for a in r.trace)


def test_transform_hop_out_of_scope_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched_hosts: list[str] = []

    def probe(url: str, *, impersonate: str, referer: str, timeout: int = 20):
        fetched_hosts.append(urlsplit(url).hostname or "")
        return _FakeResp(text=_CHALLENGE_BODY, cookies={"_abck": "x"}), None

    _patch_probe(monkeypatch, probe)

    # Allow the www.* host but NOT the m.* mobile_subdomain transform. Compare on
    # the parsed hostname (not a URL substring) — both correct and CodeQL-clean.
    def scope(u: str) -> bool:
        return (urlsplit(u).hostname or "") != "m.example.com"

    r = fetch("https://www.example.com/p", scope_check=scope, enable_playwright=False)
    # The mobile_subdomain hop must be recorded as a scope skip and never fetched.
    assert any(
        a.executor == "scope_gate" and urlsplit(a.url).hostname == "m.example.com" for a in r.trace
    )
    assert "m.example.com" not in fetched_hosts


def test_all_fail_then_browser_fallback_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(url: str, **_kw: object):
        return _FakeResp(text=_CHALLENGE_BODY, cookies={"_abck": "x"}), None

    _patch_probe(monkeypatch, probe)
    r = fetch("https://www.example.com/p", max_attempts=4, enable_playwright=True)
    assert not r.ok
    # Browser fallback ran but playwright isn't installed in the test env.
    fb = [a for a in r.trace if a.phase == "fallback"]
    assert fb
    assert fb[-1].verdict == Verdict.UNKNOWN.value


def test_max_attempts_caps_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(url: str, **_kw: object):
        return _FakeResp(text=_CHALLENGE_BODY, cookies={"_abck": "x"}), None

    _patch_probe(monkeypatch, probe)
    r = fetch("https://www.example.com/p", max_attempts=3, enable_playwright=False)
    grid = [a for a in r.trace if a.phase == "grid"]
    # Grid attempts must not exceed the cap (probe is separate).
    assert len(grid) <= 3


def test_curl_unavailable_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(url: str, **_kw: object):
        return None, "curl_cffi not installed"

    _patch_probe(monkeypatch, probe)
    r = fetch("https://example.com/p", max_attempts=2, enable_playwright=False)
    assert not r.ok
    assert r.trace[0].error == "curl_cffi not installed"


def test_to_dict_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(url: str, **_kw: object):
        return _FakeResp(text=_OK_BODY, url=url), None

    _patch_probe(monkeypatch, probe)
    d = fetch("https://example.com/p", enable_playwright=False).to_dict()
    assert set(d) == {
        "ok",
        "final_url",
        "verdict",
        "profile_used",
        "trace",
        "summary",
        "content_length",
    }
    assert isinstance(d["trace"], list)
