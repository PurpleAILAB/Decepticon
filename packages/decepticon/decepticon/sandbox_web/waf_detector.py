"""WAF-product detection from a live response.

Returns a *ranking* of ``DetectionHit(profile_id, confidence, signals)`` — never
a single verdict. A single-answer detector causes cascading wrong plans when it
misfires; the planner consumes the ranking and tries the top candidates in order.

All detectors operate on WAF-vendor artifacts (cookies / headers / server /
body strings) — never site hostnames (No-Site-Name rule). Profiles live in
``waf_profiles.yaml`` next to this module.

Derived from ``fivetaku/insane-search`` (MIT), ``engine/waf_detector.py``.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a declared dep
    yaml = None  # type: ignore[assignment]


PROFILES_PATH = os.path.join(os.path.dirname(__file__), "waf_profiles.yaml")


# In-code safety net — used when waf_profiles.yaml is missing/invalid or PyYAML
# is unavailable. Keeps fetch() working in a degraded-but-sane, site-agnostic mode.
_DEFAULT_PROFILES: dict[str, Any] = {
    "unknown_challenge": {
        "detectors": {},
        "confidence_rules": {"strong": 0, "weak": 0},
        "capabilities_needed": ["needs_js_exec"],
        "tls_impersonate_candidates": [
            ["safari", "chrome", "firefox"],
            ["safari_ios", "chrome_android"],
        ],
        "referer_strategies": ["self_root", "google_search", "none"],
        "url_transform_order": ["original", "mobile_subdomain"],
        "fallback_when_challenge": ["playwright_real_chrome"],
        "notes": "in-code default — waf_profiles.yaml unavailable",
    },
}


# Sticky last-load error; callers surface it in the result trace.
_LAST_LOAD_ERROR: str | None = None


@dataclass
class DetectionHit:
    profile_id: str
    confidence: float
    signals: list[str]


def last_load_error() -> str | None:
    """Most recent profile-loader error, or ``None`` if clean."""
    return _LAST_LOAD_ERROR


def load_profiles(path: str = PROFILES_PATH) -> dict[str, Any]:
    """Load profiles with graceful fallback. Never raises.

    On any failure (PyYAML missing, file missing, parse error, unexpected
    shape) returns a copy of ``_DEFAULT_PROFILES`` and records the reason in
    the module-level error for the caller to surface.
    """
    global _LAST_LOAD_ERROR
    _LAST_LOAD_ERROR = None

    if yaml is None:
        _LAST_LOAD_ERROR = "PyYAML not installed — using in-code default profile"
        return dict(_DEFAULT_PROFILES)
    try:
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _LAST_LOAD_ERROR = f"waf_profiles.yaml not found at {path}"
        return dict(_DEFAULT_PROFILES)
    except yaml.YAMLError as exc:
        _LAST_LOAD_ERROR = f"YAML parse error: {type(exc).__name__}: {str(exc)[:200]}"
        return dict(_DEFAULT_PROFILES)
    except OSError as exc:
        _LAST_LOAD_ERROR = f"profile loader: {type(exc).__name__}: {str(exc)[:200]}"
        return dict(_DEFAULT_PROFILES)

    if not isinstance(loaded, dict) or not any(k for k in loaded if not k.startswith("_")):
        _LAST_LOAD_ERROR = "waf_profiles.yaml has no usable profiles"
        return dict(_DEFAULT_PROFILES)

    return loaded


def _cookies_dict(resp: Any) -> dict[str, str]:
    try:
        return {c.name: c.value for c in resp.cookies.jar}
    except Exception:  # noqa: BLE001 - cookie shapes vary across HTTP clients
        try:
            return dict(resp.cookies) if hasattr(resp, "cookies") else {}
        except Exception:  # noqa: BLE001
            return {}


def _headers_dict(resp: Any) -> dict[str, str]:
    try:
        return {k.lower(): v for k, v in dict(resp.headers).items()}
    except Exception:  # noqa: BLE001 - missing/odd headers attr
        return {}


def _match_patterns(haystack_keys: list[str], patterns: list[str]) -> list[str]:
    """Match literal names or fnmatch wildcards (e.g. ``X-Akamai-*``)."""
    hits: list[str] = []
    lowered_keys = [k.lower() for k in haystack_keys]
    for pat in patterns or []:
        pat_l = pat.lower()
        if any(c in pat for c in "*?["):
            if any(fnmatch.fnmatchcase(key, pat_l) for key in lowered_keys):
                hits.append(pat)
        elif pat_l in lowered_keys:
            hits.append(pat)
    return hits


def _score_profile(profile_id: str, profile: dict[str, Any], resp: Any) -> DetectionHit | None:
    if profile_id.startswith("_"):
        return None
    detectors = profile.get("detectors") or {}
    if not detectors and profile_id != "unknown_challenge":
        return None

    cookies = _cookies_dict(resp)
    headers = _headers_dict(resp)
    body = (getattr(resp, "text", "") or "").lower()
    server = headers.get("server", "")

    signals: list[str] = []
    for hit in _match_patterns(list(cookies.keys()), detectors.get("cookie") or []):
        signals.append(f"cookie:{hit}")
    for hit in _match_patterns(list(headers.keys()), detectors.get("header") or []):
        signals.append(f"header:{hit}")
    for needle in detectors.get("server_contains") or []:
        if needle.lower() in server:
            signals.append(f"server:{needle}")
    for needle in detectors.get("body") or []:
        if needle.lower() in body:
            signals.append(f"body:{needle}")

    if not signals:
        return None

    rules = profile.get("confidence_rules") or {"strong": 2, "weak": 1}
    n = len(signals)
    if n >= rules.get("strong", 2):
        conf = 0.9
    elif n >= rules.get("weak", 1):
        conf = 0.6
    else:
        conf = 0.3
    return DetectionHit(profile_id=profile_id, confidence=conf, signals=signals)


def detect(
    resp: Any, *, profiles: dict[str, Any] | None = None, min_confidence: float = 0.0
) -> list[DetectionHit]:
    """Return a ranked list of detection hits (best first).

    When nothing fires, returns a single ``unknown_challenge`` hit at
    confidence 0.1 so the caller can fall back to conservative settings.
    """
    if profiles is None:
        profiles = load_profiles()

    hits: list[DetectionHit] = []
    for profile_id, profile in profiles.items():
        if profile_id.startswith("_"):
            continue
        hit = _score_profile(profile_id, profile, resp)
        if hit and hit.confidence >= min_confidence:
            hits.append(hit)

    hits.sort(key=lambda x: x.confidence, reverse=True)
    if not hits:
        hits.append(
            DetectionHit(profile_id="unknown_challenge", confidence=0.1, signals=["fallback"])
        )
    return hits


def load_profile(profile_id: str, *, profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get one profile by id, falling back to ``unknown_challenge``."""
    if profiles is None:
        profiles = load_profiles()
    return profiles.get(profile_id) or profiles.get("unknown_challenge") or {}
