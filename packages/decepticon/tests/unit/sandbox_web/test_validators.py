"""Unit tests for the open-web engine's 4-layer validator."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from decepticon.sandbox_web.validators import (
    SMALL_BODY_THRESHOLD,
    ValidationResult,
    Verdict,
    validate,
)


@dataclass
class _FakeResp:
    """Minimal response shim (status_code / text / cookies dict)."""

    status_code: int = 200
    text: str = ""
    cookies: dict[str, str] = field(default_factory=dict)


def _big(body: str = "x") -> str:
    """Body comfortably above SMALL_BODY_THRESHOLD."""
    return body * (SMALL_BODY_THRESHOLD + 100)


def test_non_200_is_blocked() -> None:
    r = validate(_FakeResp(status_code=403, text=_big()))
    assert r.verdict is Verdict.BLOCKED
    assert "status=403" in r.reasons


def test_status_zero_is_blocked() -> None:
    assert validate(_FakeResp(status_code=0, text="")).verdict is Verdict.BLOCKED


@pytest.mark.parametrize(
    "marker",
    ["Just a moment...", "DataDome", "The requested URL was rejected"],
)
def test_challenge_marker_detected(marker: str) -> None:
    r = validate(_FakeResp(text=_big() + marker))
    assert r.verdict is Verdict.CHALLENGE
    assert any(m.startswith("marker:") for m in r.reasons)


def test_size_fingerprint_is_challenge() -> None:
    body = "a" * 2600
    r = validate(_FakeResp(text=body), known_bad_sizes=[2600])
    assert r.verdict is Verdict.CHALLENGE
    assert any(reason.startswith("size_fp:") for reason in r.reasons)


def test_size_fingerprint_tolerance() -> None:
    body = "a" * 2610
    assert validate(_FakeResp(text=body), known_bad_sizes=[2600]).verdict is Verdict.CHALLENGE
    # Outside tolerance → not a fingerprint match (large body → weak_ok).
    big = "a" * (SMALL_BODY_THRESHOLD + 500)
    assert validate(_FakeResp(text=big), known_bad_sizes=[2600]).verdict is Verdict.WEAK_OK


def test_selector_match_is_strong_ok() -> None:
    html = _big() + "<article id='post'>hello</article>"
    r = validate(_FakeResp(text=html), success_selectors=["article#post"])
    assert r.verdict is Verdict.STRONG_OK
    assert "article#post" in r.matched_selectors


def test_selector_requested_but_absent_is_challenge() -> None:
    r = validate(_FakeResp(text=_big()), success_selectors=["article#post"])
    assert r.verdict is Verdict.CHALLENGE
    assert "no_success_selector" in r.reasons


def test_selector_match_with_unresolved_abck_demotes_to_weak_ok() -> None:
    html = "<article id='post'>x</article>"
    resp = _FakeResp(text=html, cookies={"_abck": "abc~-1~xyz"})
    r = validate(resp, success_selectors=["article#post"])
    assert r.verdict is Verdict.WEAK_OK
    assert "abck_unresolved" in r.reasons


def test_tiny_body_without_selectors_is_challenge() -> None:
    r = validate(_FakeResp(text="tiny"))
    assert r.verdict is Verdict.CHALLENGE
    assert any(reason.startswith("tiny_body:") for reason in r.reasons)


def test_large_body_without_selectors_is_weak_ok() -> None:
    assert validate(_FakeResp(text=_big())).verdict is Verdict.WEAK_OK


def test_http_200_is_not_success_without_proof() -> None:
    # The core principle: a 200 with a challenge marker is NOT ok.
    r = validate(_FakeResp(status_code=200, text=_big() + "captcha"))
    assert not r.ok


def test_malformed_response_is_unknown() -> None:
    class _Bad:
        @property
        def status_code(self) -> int:
            raise RuntimeError("boom")

    r = validate(_Bad())
    assert r.verdict is Verdict.UNKNOWN
    assert any(reason.startswith("parse_error:") for reason in r.reasons)


def test_to_dict_round_trips_fields() -> None:
    r = ValidationResult(verdict=Verdict.WEAK_OK, body_size=10, status=200)
    d = r.to_dict()
    assert d["verdict"] == "weak_ok"
    assert d["status"] == 200
