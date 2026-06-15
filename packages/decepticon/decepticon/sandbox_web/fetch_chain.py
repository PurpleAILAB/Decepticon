"""Generic open-web fetch chain — the engine's single entrypoint.

    from decepticon.sandbox_web.fetch_chain import fetch
    result = fetch("https://example.com/path", success_selectors=["article"])

Phases (kept explicit so tests/trace can target each): probe → detect → plan →
execute (grid) → fallback (browser) → report. ``FetchResult.trace`` records
every attempt (transform × impersonate × referer × executor).

No site-specific branching (No-Site-Name rule). Site knowledge enters only via
``success_selectors`` / ``user_hint``. **RoE is enforced per hop**: an optional
``scope_check`` predicate gates every transformed/redirected host; an
out-of-scope hop is skipped fail-closed (never attempted). The sandbox-edge
nftables allowlist is the authoritative backstop; this is defense-in-depth and
avoids wasting attempts on hosts the network layer would drop anyway.

Engine derived from ``fivetaku/insane-search`` (MIT), ``engine/fetch_chain.py``;
the ``scope_check`` RoE gate is the Decepticon adaptation.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit

from decepticon.sandbox_web.url_transforms import iter_transformed
from decepticon.sandbox_web.validators import Verdict, validate
from decepticon.sandbox_web.waf_detector import (
    DetectionHit,
    detect,
    last_load_error,
    load_profile,
    load_profiles,
)

# A predicate that returns True if a URL is in RoE scope. Injected by the caller
# (the CLI builds it from roe.json); None means "no scope gate" (unit tests,
# standalone use) — the sandbox nftables allowlist still applies in production.
ScopeCheck = Callable[[str], bool]


def _self_root(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


REFERER_STRATEGIES: dict[str, Callable[[str], str]] = {
    "self_root": _self_root,
    "google_search": lambda _url: "https://www.google.com/",
    "none": lambda _url: "",
}


@dataclass
class Attempt:
    phase: str  # probe | grid | fallback
    executor: str  # curl_cffi | playwright_real_chrome | ...
    url: str
    url_transform: str
    impersonate: str | None
    referer: str
    status: int = 0
    body_size: int = 0
    verdict: str = ""
    reasons: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchResult:
    ok: bool
    content: str = ""
    final_url: str = ""
    verdict: str = ""
    profile_used: str | None = None
    trace: list[Attempt] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "final_url": self.final_url,
            "verdict": self.verdict,
            "profile_used": self.profile_used,
            "trace": [a.to_dict() for a in self.trace],
            "summary": self.summary,
            "content_length": len(self.content),
        }


def _scope_skip(url: str, transform: str, phase: str) -> Attempt:
    """An Attempt record for a hop refused by the RoE scope gate (fail-closed)."""
    return Attempt(
        phase=phase,
        executor="scope_gate",
        url=url,
        url_transform=transform,
        impersonate=None,
        referer="",
        verdict=Verdict.BLOCKED.value,
        reasons=["out_of_roe_scope"],
    )


def _curl_probe(
    url: str, *, impersonate: str, referer: str, timeout: int = 20
) -> tuple[Any, str | None]:
    """One curl_cffi GET. Returns (response, error). response is None on failure.

    curl_cffi is a sandbox-image dependency; unit tests monkeypatch this fn.
    """
    try:
        from curl_cffi import requests as cffi_requests  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None, "curl_cffi not installed"

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    try:
        resp = cffi_requests.get(
            url, impersonate=impersonate, headers=headers, timeout=timeout, allow_redirects=True
        )
        return resp, None
    except Exception as exc:  # noqa: BLE001 - network/curl errors must not crash the grid
        return None, f"{type(exc).__name__}:{str(exc)[:200]}"


def _run_attempt(
    url: str,
    *,
    transform_name: str,
    impersonate: str,
    referer_name: str,
    success_selectors: list[str] | None,
    known_bad_sizes: list[int] | None,
    timeout: int,
    phase: str,
) -> tuple[Attempt, Any]:
    referer_url = REFERER_STRATEGIES.get(referer_name, REFERER_STRATEGIES["none"])(url)
    t0 = time.time()
    resp, err = _curl_probe(url, impersonate=impersonate, referer=referer_url, timeout=timeout)
    att = Attempt(
        phase=phase,
        executor="curl_cffi",
        url=url,
        url_transform=transform_name,
        impersonate=impersonate,
        referer=referer_name,
        elapsed_s=round(time.time() - t0, 3),
    )
    if err or resp is None:
        att.error = err or "no response"
        att.verdict = Verdict.UNKNOWN.value
        return att, None

    vr = validate(resp, success_selectors=success_selectors, known_bad_sizes=known_bad_sizes)
    att.status = vr.status
    att.body_size = vr.body_size
    att.verdict = vr.verdict.value
    att.reasons = vr.reasons
    return att, resp


def _build_result(
    resp: Any, attempt: Attempt, trace: list[Attempt], profile_used: str | None
) -> FetchResult:
    return FetchResult(
        ok=True,
        content=getattr(resp, "text", "") or "",
        final_url=str(getattr(resp, "url", attempt.url)),
        verdict=attempt.verdict,
        profile_used=profile_used,
        trace=trace,
        summary=(
            f"{attempt.executor} {attempt.impersonate} + {attempt.url_transform} "
            f"+ referer:{attempt.referer} → {attempt.verdict}"
        ),
    )


def _jitter() -> None:
    jmin = int(os.environ.get("DECEPTICON_WEB_JITTER_MS_MIN", "150"))
    jmax = int(os.environ.get("DECEPTICON_WEB_JITTER_MS_MAX", "400"))
    time.sleep(random.uniform(jmin / 1000.0, jmax / 1000.0))


def fetch(
    url: str,
    *,
    success_selectors: list[str] | None = None,
    device_class: str = "auto",
    user_hint: dict[str, Any] | None = None,
    timeout: int = 25,
    max_attempts: int = 12,
    scope_check: ScopeCheck | None = None,
    enable_playwright: bool = True,
) -> FetchResult:
    """Fetch ``url`` via the escalating grid, RoE-gated per hop.

    ``scope_check`` — predicate returning True if a URL is in engagement scope.
    Every transformed/redirected hop is checked; out-of-scope hops are skipped
    fail-closed. ``None`` disables the in-engine gate (the sandbox nftables
    allowlist remains authoritative in production).
    """
    user_hint = user_hint or {}
    profiles = load_profiles()
    trace: list[Attempt] = []
    profile_used: str | None = None

    if scope_check is not None and not scope_check(url):
        trace.append(_scope_skip(url, "original", "probe"))
        return FetchResult(
            ok=False,
            verdict=Verdict.BLOCKED.value,
            trace=trace,
            summary="refused: input URL is outside engagement RoE scope",
        )

    load_err = last_load_error()
    if load_err:
        trace.append(
            Attempt(
                phase="probe",
                executor="profile_loader",
                url=url,
                url_transform="original",
                impersonate=None,
                referer="",
                verdict=Verdict.UNKNOWN.value,
                error=f"profiles_fallback: {load_err}",
            )
        )

    # -------- Phase 1: probe --------
    base_impersonate = user_hint.get("impersonate_first") or (
        "safari_ios" if device_class == "mobile" else "safari"
    )
    base_referer = user_hint.get("referer_strategy") or "self_root"
    probe_attempt, probe_resp = _run_attempt(
        url,
        transform_name="original",
        impersonate=base_impersonate,
        referer_name=base_referer,
        success_selectors=success_selectors,
        known_bad_sizes=None,
        timeout=timeout,
        phase="probe",
    )
    trace.append(probe_attempt)
    last_resp = probe_resp
    if probe_resp is not None and probe_attempt.verdict in (
        Verdict.STRONG_OK.value,
        Verdict.WEAK_OK.value,
    ):
        return _build_result(probe_resp, probe_attempt, trace, profile_used=None)

    # -------- Phase 2: detect + grid --------
    hits = (
        detect(last_resp, profiles=profiles)
        if last_resp is not None
        else [
            DetectionHit(
                profile_id="unknown_challenge", confidence=0.1, signals=["no_probe_response"]
            )
        ]
    )
    attempts_used = len(trace)
    for hit in hits[:3]:
        if attempts_used >= max_attempts:
            break
        profile_id = hit.profile_id
        profile_used = profile_id
        profile = load_profile(profile_id, profiles=profiles)

        tls_groups: list[list[str]] = profile.get("tls_impersonate_candidates") or [
            ["safari", "chrome"]
        ]
        tls_flat = [t for group in tls_groups for t in group]
        avoid = set(profile.get("tls_impersonate_avoid") or [])
        tls_flat = [t for t in tls_flat if t not in avoid]
        referer_order = profile.get("referer_strategies") or ["self_root"]
        transform_order = profile.get("url_transform_order") or ["original"]

        if device_class == "mobile":
            tls_flat = [t for t in tls_flat if "ios" in t or "android" in t] or tls_flat
            if "mobile_subdomain" not in transform_order:
                transform_order = [*transform_order, "mobile_subdomain"]
        elif device_class == "desktop":
            tls_flat = [t for t in tls_flat if "ios" not in t and "android" not in t] or tls_flat

        known_bad_sizes = profile.get("known_bad_sizes") or None

        for t_name, t_url in iter_transformed(url, transform_order):
            # RoE: a transform can change the host (e.g. www.→m.) — re-gate it.
            if scope_check is not None and not scope_check(t_url):
                trace.append(_scope_skip(t_url, t_name, "grid"))
                continue
            for tls in tls_flat:
                for ref in referer_order:
                    if attempts_used >= max_attempts:
                        break
                    if t_name == "original" and tls == base_impersonate and ref == base_referer:
                        continue  # skip exact duplicate of the probe
                    att, resp = _run_attempt(
                        t_url,
                        transform_name=t_name,
                        impersonate=tls,
                        referer_name=ref,
                        success_selectors=success_selectors,
                        known_bad_sizes=known_bad_sizes,
                        timeout=timeout,
                        phase="grid",
                    )
                    trace.append(att)
                    attempts_used += 1
                    _jitter()
                    if resp is None:
                        continue
                    last_resp = resp
                    if att.verdict in (Verdict.STRONG_OK.value, Verdict.WEAK_OK.value):
                        return _build_result(resp, att, trace, profile_used=profile_id)

    # -------- Phase 3: browser fallback --------
    if enable_playwright:
        fb_attempt, fb_content = _run_browser_fallback(
            url, profile_used, success_selectors, device_class, scope_check, trace
        )
        if fb_attempt is not None and fb_attempt.verdict in (
            Verdict.STRONG_OK.value,
            Verdict.WEAK_OK.value,
        ):
            return FetchResult(
                ok=True,
                content=fb_content,
                final_url=fb_attempt.url,
                verdict=fb_attempt.verdict,
                profile_used=profile_used,
                trace=trace,
                summary=f"browser fallback succeeded via {fb_attempt.executor}",
            )

    # -------- Give up --------
    last_attempt = trace[-1] if trace else None
    return FetchResult(
        ok=False,
        content=getattr(last_resp, "text", "") if last_resp is not None else "",
        final_url=str(getattr(last_resp, "url", url)) if last_resp is not None else url,
        verdict=last_attempt.verdict if last_attempt else Verdict.UNKNOWN.value,
        profile_used=profile_used,
        trace=trace,
        summary=_format_summary(trace, profile_used),
    )


def _run_browser_fallback(
    url: str,
    profile_used: str | None,
    success_selectors: list[str] | None,
    device_class: str,
    scope_check: ScopeCheck | None,
    trace: list[Attempt],
) -> tuple[Attempt | None, str]:
    """Run the browser tier; append attempts to ``trace``.

    Returns ``(winning_attempt, content)`` on success, else ``(last_attempt, "")``.
    """
    if scope_check is not None and not scope_check(url):
        skip = _scope_skip(url, "original", "fallback")
        trace.append(skip)
        return skip, ""
    try:
        from decepticon.sandbox_web.executor import run_browser_fallback
    except ImportError as exc:
        att = Attempt(
            phase="fallback",
            executor="browser",
            url=url,
            url_transform="original",
            impersonate=None,
            referer="",
            verdict=Verdict.UNKNOWN.value,
            error=f"executor unavailable: {exc}",
        )
        trace.append(att)
        return att, ""

    profiles = load_profiles()
    fb_profile = load_profile(profile_used or "unknown_challenge", profiles=profiles)
    fb_order = fb_profile.get("fallback_when_challenge") or ["playwright_real_chrome"]
    last: Attempt | None = None
    for fb_name in fb_order:
        if fb_name == "curl_grid_exhaust":
            continue
        att, content = run_browser_fallback(
            url,
            success_selectors=success_selectors,
            device_class=device_class,
            force_executor=fb_name,
        )
        trace.append(att)
        last = att
        if att.verdict in (Verdict.STRONG_OK.value, Verdict.WEAK_OK.value):
            return att, content
    return last, ""


def _format_summary(trace: list[Attempt], profile: str | None) -> str:
    n = len(trace)
    verdicts = [a.verdict for a in trace]
    head = ",".join(verdicts[:5]) + ("..." if n > 5 else "")
    return f"failed after {n} attempts; profile={profile}; verdicts={head}"
