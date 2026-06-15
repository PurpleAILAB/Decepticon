"""Generic challenge / success validator for the open-web engine.

Four layers, all site-agnostic (No-Site-Name rule — never a site brand/domain):

  1. Challenge markers — WAF *product* strings ("Just a moment...", DataDome…).
  2. Size fingerprints — known bad byte sizes hinted by the caller/profile.
  3. Cookie sensor state — e.g. Akamai ``_abck=~-1~`` (sensor never resolved).
  4. ``success_selectors`` — caller-supplied positive proof (strongest).

Layers 1-3 are negative proof (fail fast). Layer 4 is positive proof — without
it, an HTTP 200 is only a *weak* success. The whole point: **HTTP 200 is an
inspection-start condition, not a success declaration.**

Derived from ``fivetaku/insane-search`` (MIT), ``engine/validators.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:  # bs4 is a soft dep — only needed when success_selectors are supplied.
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - exercised in deps-missing path
    BeautifulSoup = None  # type: ignore[assignment, misc]


# Markers are WAF-product strings only. NEVER a site brand / domain.
CHALLENGE_MARKERS: list[str] = [
    "Access Denied",
    "sec-if-cpt-container",
    "Powered and protected by Akamai",
    "Just a moment...",
    "Checking your browser",
    "cf-chl-bypass",
    "Attention Required! | Cloudflare",
    "<title>Bot Challenge</title>",
    "DataDome",
    "captcha",
    "Please enable JS and disable any ad blocker",
    "The requested URL was rejected",
    "Request unsuccessful. Incapsula",
]

# Minimum body size below which a 200 is suspected to be a stub / challenge page.
# Callers that legitimately expect tiny responses should pass success_selectors.
SMALL_BODY_THRESHOLD = 3000


class Verdict(Enum):
    """Five-level classification — avoids a misleading ok/not-ok binary."""

    STRONG_OK = "strong_ok"  # passes all layers incl. success_selectors
    WEAK_OK = "weak_ok"  # passes 1-3 but no positive proof available
    CHALLENGE = "challenge"  # fails 1-3 (negative proof triggered)
    BLOCKED = "blocked"  # non-200 status
    UNKNOWN = "unknown"  # exception / malformed response / missing dep


@dataclass
class ValidationResult:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    matched_selectors: list[str] = field(default_factory=list)
    body_size: int = 0
    status: int = 0

    @property
    def ok(self) -> bool:
        """Ergonomic ``if vr.ok`` — weak_ok still counts as ok."""
        return self.verdict in (Verdict.STRONG_OK, Verdict.WEAK_OK)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasons": self.reasons,
            "matched_selectors": self.matched_selectors,
            "body_size": self.body_size,
            "status": self.status,
        }


def _marker_hits(body_lower: str) -> list[str]:
    return [m for m in CHALLENGE_MARKERS if m.lower() in body_lower]


def _abck_unresolved(cookies: dict[str, str]) -> bool:
    abck = cookies.get("_abck", "")
    return bool(abck) and "~-1~" in abck


def _selector_hits(body: str, selectors: list[str]) -> list[str] | None:
    """Matched-selector list, or ``None`` when BeautifulSoup is unavailable.

    Distinguishing ``None`` (dependency missing) from ``[]`` (nothing matched)
    lets the caller classify UNKNOWN vs CHALLENGE correctly — a missing dep
    must never masquerade as a WAF outcome.
    """
    if BeautifulSoup is None:
        return None
    try:
        soup = BeautifulSoup(body, "html.parser")
    except Exception:  # noqa: BLE001 - malformed HTML must not crash validation
        return []
    hits: list[str] = []
    for sel in selectors:
        try:
            if soup.select(sel):
                hits.append(sel)
        except Exception:  # noqa: BLE001 - a bad selector skips, never crashes
            continue
    return hits


def _extract_cookies(resp: Any) -> dict[str, str]:
    try:
        return {c.name: c.value for c in resp.cookies.jar}
    except Exception:  # noqa: BLE001 - cookie shapes vary across HTTP clients
        try:
            return dict(resp.cookies) if hasattr(resp, "cookies") else {}
        except Exception:  # noqa: BLE001
            return {}


def validate(
    resp: Any,
    *,
    success_selectors: list[str] | None = None,
    known_bad_sizes: list[int] | None = None,
    size_tolerance: int = 20,
) -> ValidationResult:
    """Validate an HTTP response object (``curl_cffi`` / ``requests`` shaped).

    Parameters
    ----------
    resp
        Object exposing ``status_code``, ``text``, and cookie-like access.
    success_selectors
        Caller positive proof. Any match promotes ``weak_ok`` → ``strong_ok``.
        Absence still allows ``weak_ok`` (no positive proof, no negative proof).
    known_bad_sizes
        Byte sizes empirically observed as challenge-page fingerprints. These
        decay over time; profiles should refresh them.
    """
    try:
        status = int(getattr(resp, "status_code", 0) or 0)
        text = getattr(resp, "text", "") or ""
        size = len(text)
    except Exception as exc:  # noqa: BLE001 - malformed response object
        return ValidationResult(verdict=Verdict.UNKNOWN, reasons=[f"parse_error:{exc}"])

    result = ValidationResult(verdict=Verdict.UNKNOWN, body_size=size, status=status)

    if status == 0 or status >= 400:
        result.verdict = Verdict.BLOCKED
        result.reasons.append(f"status={status}")
        return result

    # --- Layer 1: challenge markers (product strings, never site brand) ---
    markers = _marker_hits(text.lower())
    if markers:
        result.verdict = Verdict.CHALLENGE
        result.reasons.extend(f"marker:{m}" for m in markers[:3])
        return result

    # --- Layer 2: size fingerprints (caller hint, tolerant match) ---
    # A fingerprint match is a strong negative signal — it overrides selectors.
    if known_bad_sizes:
        for bad in known_bad_sizes:
            if abs(size - bad) <= size_tolerance:
                result.verdict = Verdict.CHALLENGE
                result.reasons.append(f"size_fp:{size}~{bad}")
                return result

    # --- Layer 4 (early): caller's positive proof overrides size heuristic ---
    if success_selectors:
        hits = _selector_hits(text, success_selectors)
        if hits is None:
            # bs4 missing — cannot evaluate proof; UNKNOWN, not a faked WAF verdict.
            result.verdict = Verdict.UNKNOWN
            result.reasons.append("bs4_missing")
            return result
        if hits:
            result.matched_selectors = hits
            # Unresolved Akamai sensor demotes even a selector match: the body
            # carries our expected element but the session was never accepted.
            if _abck_unresolved(_extract_cookies(resp)):
                result.reasons.append("abck_unresolved")
                result.verdict = Verdict.WEAK_OK
                return result
            result.verdict = Verdict.STRONG_OK
            return result
        # Selectors requested but none matched → challenge regardless of size.
        result.verdict = Verdict.CHALLENGE
        result.reasons.append("no_success_selector")
        return result

    # No selectors: fall back to the size heuristic.
    if size < SMALL_BODY_THRESHOLD:
        result.verdict = Verdict.CHALLENGE
        result.reasons.append(f"tiny_body:{size}")
        return result

    # --- Layer 3: cookie sensor state (only when no selectors decide it) ---
    if _abck_unresolved(_extract_cookies(resp)):
        result.reasons.append("abck_unresolved")

    # No positive proof available — weak OK.
    result.verdict = Verdict.WEAK_OK
    return result
