"""Browser-tier fallback for the fetch chain — runs INSIDE the sandbox.

When the curl_cffi grid cannot punch through (JS challenge, real-TLS detection),
the chain escalates here. Because the engine itself runs in the sandbox, the
browser tier is a **local Playwright** (Chromium) in the same container — there
is no Playwright-MCP path (MCP is a Claude-session concept and would route
egress through the management process, violating the sandbox-only invariant).

Playwright is an *optional* tier (ADR-0010): if it is not installed in the
sandbox image, this returns a clear UNKNOWN attempt rather than crashing — the
curl grid result still stands.

Derived from ``fivetaku/insane-search`` (MIT), ``engine/executor.py``; the
MCP/local-node split is replaced by a single in-sandbox local-Playwright path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from decepticon.sandbox_web.fetch_chain import Attempt
from decepticon.sandbox_web.validators import Verdict, validate


@dataclass
class _PageResp:
    """Minimal response shim so validators.validate() works on rendered HTML.

    Rendered pages have no meaningful raw cookie sensor to inspect, so cookies
    is an empty dict (validators falls back to size/selector layers).
    """

    text: str
    status_code: int = 200
    url: str = ""
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


def _render_with_playwright(
    url: str, *, device_class: str, wait_selector: str | None, timeout_ms: int
) -> tuple[str, str] | None:
    """Render ``url`` with local Chromium. Returns (html, final_url) or None.

    Returns None when Playwright is unavailable (optional tier).
    """
    try:
        from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context_kwargs: dict[str, Any] = {}
            if device_class == "mobile":
                context_kwargs = {**p.devices["iPhone 13 Pro"]}
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 10_000))
                except Exception:  # noqa: BLE001 - selector may never appear; take what we have
                    pass
            html = page.content()
            final_url = page.url
            context.close()
            browser.close()
            return html, final_url
    except Exception as exc:  # noqa: BLE001 - browser crashes must not kill the chain
        raise _BrowserError(f"{type(exc).__name__}:{str(exc)[:200]}") from exc


class _BrowserError(RuntimeError):
    pass


def run_browser_fallback(
    url: str,
    *,
    success_selectors: list[str] | None = None,
    device_class: str = "auto",
    timeout: int = 60,
    force_executor: str | None = None,
) -> tuple[Attempt, str]:
    """Render ``url`` with local Chromium and validate the result.

    Returns ``(Attempt, html)``. ``Attempt.verdict`` reflects validation; html
    is ``""`` when the browser tier is unavailable or failed.
    """
    executor_name = force_executor or "playwright_local_chrome"
    t0 = time.time()
    att = Attempt(
        phase="fallback",
        executor=executor_name,
        url=url,
        url_transform="original",
        impersonate=None,
        referer="",
    )

    wait_selector = success_selectors[0] if success_selectors else None
    try:
        rendered = _render_with_playwright(
            url,
            device_class=device_class,
            wait_selector=wait_selector,
            timeout_ms=timeout * 1000,
        )
    except _BrowserError as exc:
        att.error = str(exc)
        att.verdict = Verdict.UNKNOWN.value
        att.elapsed_s = round(time.time() - t0, 3)
        return att, ""

    att.elapsed_s = round(time.time() - t0, 3)
    if rendered is None:
        att.error = "playwright not installed in sandbox image (optional browser tier)"
        att.verdict = Verdict.UNKNOWN.value
        return att, ""

    html, final_url = rendered
    vr = validate(_PageResp(text=html, url=final_url), success_selectors=success_selectors)
    att.url = final_url or url
    att.status = 200
    att.body_size = len(html)
    att.verdict = vr.verdict.value
    att.reasons = vr.reasons
    return att, html
