"""``browser_action`` — single multiplex tool for persistent Playwright.

Sub-actions: ``launch``, ``goto``, ``click``, ``type``, ``scroll``,
``screenshot``, ``eval_js``, ``console_logs``, ``page_source``, ``pdf``,
``list_tabs``, ``switch_tab``, ``close``.

State (Browser, Context, Pages, console buffer) lives in a per-process
:class:`BrowserSessionManager` accessed through :func:`get_session_manager`.
Each sub-action returns a JSON string so the LLM sees structured output;
errors are caught and returned as ``{"error": "..."}`` rather than
raised so the agent loop continues.

Playwright is imported lazily on first use. If Playwright is not
installed the tool returns an instructive error pointing operators at
the ``decepticon[browser]`` extra (which will be added by a follow-up
PR alongside the sandbox-image install).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

log = logging.getLogger(__name__)

# Per-handle close timeout: one hung Playwright handle must not wedge cleanup.
_CLOSE_TIMEOUT_S = 5.0


async def _safe_close(
    obj: Any,
    name: str,
    *,
    timeout: float = _CLOSE_TIMEOUT_S,
    method: str = "close",
) -> None:
    """Await ``obj.<method>()`` with a bounded timeout, logging any failure.

    Replaces silent ``except Exception: pass`` blocks: a hung handle is
    cancelled after ``timeout`` seconds and every failure is recorded so
    operators can diagnose leaks instead of seeing the resource vanish.
    """
    if obj is None:
        return
    close_fn: Callable[[], Awaitable[Any]] = getattr(obj, method)
    try:
        await asyncio.wait_for(close_fn(), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning(
            "browser cleanup: %s.%s() timed out after %.2fs; abandoning handle",
            name,
            method,
            timeout,
        )
    except Exception as exc:  # noqa: BLE001 — close paths must never re-raise
        log.warning("browser cleanup: %s.%s() failed: %s", name, method, exc)


class BrowserActionError(RuntimeError):
    """Raised internally by the manager; caught at the tool boundary.

    Converted to ``{"error": "..."}`` JSON so the LLM can reason about
    Playwright-missing / page-closed / navigation-timeout / bad-selector
    failures without terminating the agent run.
    """


_SUPPORTED_ACTIONS = frozenset(
    {
        "launch",
        "goto",
        "click",
        "type",
        "scroll",
        "screenshot",
        "eval_js",
        "console_logs",
        "page_source",
        "pdf",
        "list_tabs",
        "switch_tab",
        "close",
    }
)


@dataclass(slots=True)
class _Tab:
    """One Playwright page tracked by the session manager.

    The ``console`` deque is bounded so a chatty page cannot drive
    memory growth without bound; ``len`` is exposed to the LLM via
    ``console_logs`` so the agent knows when older lines were dropped.
    """

    page: Any
    console: deque[str] = field(default_factory=lambda: deque(maxlen=500))


class BrowserSessionManager:
    """Per-process singleton holding the live Playwright browser state.

    All public methods are async and serialize through a per-instance
    asyncio lock so concurrent ``browser_action(...)`` calls from
    different tool turns cannot interleave navigation against the same
    page.
    """

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._tabs: dict[str, _Tab] = {}
        self._active: str | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _import_playwright() -> Any:
        try:
            from playwright import async_api
        except ImportError as exc:
            raise BrowserActionError(
                "Playwright is not installed. Add the 'browser' extra or install "
                "playwright + chromium in the sandbox image."
            ) from exc
        return async_api

    async def _ensure_browser(self, headless: bool = True) -> None:
        if self._browser is not None:
            return
        api = self._import_playwright()
        self._playwright = await api.async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self._context = await self._browser.new_context()

    async def launch(self, headless: bool = True) -> dict[str, Any]:
        async with self._lock:
            await self._ensure_browser(headless=headless)
            if not self._tabs:
                await self._new_tab("main")
            return {"tabs": list(self._tabs.keys()), "active": self._active}

    async def _new_tab(self, tab_id: str) -> _Tab:
        page = await self._context.new_page()
        tab = _Tab(page=page)
        page.on("console", lambda msg: tab.console.append(f"[{msg.type}] {msg.text}"))
        self._tabs[tab_id] = tab
        self._active = tab_id
        return tab

    def _active_tab(self) -> _Tab:
        if self._active is None or self._active not in self._tabs:
            raise BrowserActionError("No active tab. Call browser_action(action='launch') first.")
        return self._tabs[self._active]

    async def goto(self, url: str, timeout_ms: int = 30000) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            response = await tab.page.goto(url, timeout=timeout_ms, wait_until="load")
            return {
                "url": tab.page.url,
                "status": response.status if response is not None else None,
                "title": await tab.page.title(),
            }

    async def click(self, selector: str, timeout_ms: int = 15000) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            await tab.page.click(selector, timeout=timeout_ms)
            return {"clicked": selector, "url": tab.page.url}

    async def type_text(
        self, selector: str, text: str, delay_ms: int = 0, timeout_ms: int = 15000
    ) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            await tab.page.fill(selector, text, timeout=timeout_ms)
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000.0)
            return {"typed_into": selector, "chars": len(text)}

    async def scroll(self, dx: int = 0, dy: int = 0) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            await tab.page.evaluate("([dx, dy]) => window.scrollBy(dx, dy)", [dx, dy])
            return {"scrolled": {"dx": dx, "dy": dy}, "url": tab.page.url}

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            png = await tab.page.screenshot(full_page=full_page)
            return {
                "format": "png",
                "bytes": len(png),
                "base64": base64.b64encode(png).decode("ascii"),
            }

    async def eval_js(self, expression: str) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            result = await tab.page.evaluate(expression)
            return {"result": result}

    async def console_logs(self, clear: bool = False) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            lines = list(tab.console)
            if clear:
                tab.console.clear()
            return {"count": len(lines), "lines": lines}

    async def page_source(self) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            html = await tab.page.content()
            return {"url": tab.page.url, "bytes": len(html), "html": html}

    async def pdf(self) -> dict[str, Any]:
        async with self._lock:
            tab = self._active_tab()
            data = await tab.page.pdf()
            return {
                "format": "pdf",
                "bytes": len(data),
                "base64": base64.b64encode(data).decode("ascii"),
            }

    async def list_tabs(self) -> dict[str, Any]:
        async with self._lock:
            return {"tabs": list(self._tabs.keys()), "active": self._active}

    async def switch_tab(self, tab_id: str) -> dict[str, Any]:
        async with self._lock:
            if tab_id not in self._tabs:
                await self._new_tab(tab_id)
            else:
                self._active = tab_id
            return {"active": self._active}

    async def close(self) -> dict[str, Any]:
        async with self._lock:
            for tab_id, tab in self._tabs.items():
                await _safe_close(tab.page, f"page[{tab_id}]")
            self._tabs.clear()
            self._active = None
            await _safe_close(self._context, "context")
            self._context = None
            await _safe_close(self._browser, "browser")
            self._browser = None
            await _safe_close(self._playwright, "playwright", method="stop")
            self._playwright = None
            return {"closed": True}


_manager: BrowserSessionManager | None = None
_manager_lock = threading.Lock()


def get_session_manager() -> BrowserSessionManager:
    """Return the process-wide :class:`BrowserSessionManager` singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = BrowserSessionManager()
        return _manager


def _reset_session_manager_for_tests() -> None:
    """Test-only: drop the singleton so each test gets a fresh manager."""
    global _manager
    with _manager_lock:
        _manager = None


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


async def _dispatch(action: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    if action not in _SUPPORTED_ACTIONS:
        raise BrowserActionError(
            f"Unknown action '{action}'. Supported: {sorted(_SUPPORTED_ACTIONS)}"
        )
    mgr = get_session_manager()
    if action == "launch":
        return await mgr.launch(headless=bool(kwargs.get("headless", True)))
    if action == "goto":
        return await mgr.goto(
            url=str(kwargs["url"]),
            timeout_ms=int(kwargs.get("timeout_ms", 30000)),
        )
    if action == "click":
        return await mgr.click(
            selector=str(kwargs["selector"]),
            timeout_ms=int(kwargs.get("timeout_ms", 15000)),
        )
    if action == "type":
        return await mgr.type_text(
            selector=str(kwargs["selector"]),
            text=str(kwargs["text"]),
            delay_ms=int(kwargs.get("delay_ms", 0)),
            timeout_ms=int(kwargs.get("timeout_ms", 15000)),
        )
    if action == "scroll":
        return await mgr.scroll(dx=int(kwargs.get("dx", 0)), dy=int(kwargs.get("dy", 0)))
    if action == "screenshot":
        return await mgr.screenshot(full_page=bool(kwargs.get("full_page", False)))
    if action == "eval_js":
        return await mgr.eval_js(expression=str(kwargs["expression"]))
    if action == "console_logs":
        return await mgr.console_logs(clear=bool(kwargs.get("clear", False)))
    if action == "page_source":
        return await mgr.page_source()
    if action == "pdf":
        return await mgr.pdf()
    if action == "list_tabs":
        return await mgr.list_tabs()
    if action == "switch_tab":
        return await mgr.switch_tab(tab_id=str(kwargs["tab_id"]))
    if action == "close":
        return await mgr.close()
    raise BrowserActionError(f"unreachable: {action}")


@tool
async def browser_action(action: str, params_json: str = "{}") -> str:
    """Drive a persistent Playwright browser session for SPA / auth / DOM work.

    Supported actions (pass parameters as a JSON string via ``params_json``):

    * ``launch`` — open the browser; optional ``headless`` (default true).
    * ``goto`` — navigate; requires ``url``; optional ``timeout_ms``.
    * ``click`` — click a CSS selector; requires ``selector``.
    * ``type`` — type into a selector; requires ``selector`` + ``text``.
    * ``scroll`` — scroll the active page by ``dx`` / ``dy`` pixels.
    * ``screenshot`` — return base64 PNG; optional ``full_page``.
    * ``eval_js`` — evaluate JS; requires ``expression``.
    * ``console_logs`` — return captured console messages; optional ``clear``.
    * ``page_source`` — return the active page's HTML.
    * ``pdf`` — render the page as PDF (base64).
    * ``list_tabs`` — list tracked tabs and the active tab id.
    * ``switch_tab`` — switch to / create tab; requires ``tab_id``.
    * ``close`` — close the browser and reset state.

    Returns a JSON string. Errors are returned as ``{"error": "..."}``
    rather than raised so the LLM can handle them in-band.
    """
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as exc:
        return _json({"error": f"params_json is not valid JSON: {exc}"})
    if not isinstance(params, dict):
        return _json({"error": "params_json must decode to a JSON object."})

    try:
        result = await _dispatch(action, params)
    except BrowserActionError as exc:
        return _json({"error": str(exc)})
    except KeyError as exc:
        return _json({"error": f"missing required parameter: {exc!s}"})
    except Exception as exc:  # noqa: BLE001
        return _json({"error": f"{type(exc).__name__}: {exc}"})
    return _json(result)


BROWSER_TOOLS = [browser_action]


__all__ = [
    "BROWSER_TOOLS",
    "BrowserActionError",
    "BrowserSessionManager",
    "browser_action",
    "get_session_manager",
]
