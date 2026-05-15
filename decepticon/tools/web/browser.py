"""Browser automation tool for the agent — Strix Playwright parity.

Wraps Playwright (lazy-imported, so the rest of Decepticon doesn't grow
a hard dependency just to ship the proxy + agent state primitives) into
a small surface the LLM can drive turn-by-turn:

  * ``open_page`` / ``close_page`` — multi-tab management
  * ``navigate`` / ``current_url`` — URL bar
  * ``click`` / ``fill`` / ``press`` — DOM interaction
  * ``screenshot`` — base64 PNG capture
  * ``evaluate`` — run JS in the page context (for XSS PoC validation)
  * ``cookies`` — read / set the active page's cookie jar

Use cases the existing httpx-based tooling can't cover:

  * **Reflected XSS validation** — actually trigger the alert and
    capture the dialog text, instead of guessing from a 200 OK body.
  * **CSRF / SameSite testing** — drive a third-party login flow
    end-to-end.
  * **Auth flow / OAuth** — follow ``window.location`` chains the
    httpx client can't follow without per-step decisions.
  * **DOM XSS / clobbering** — execute attacker JS in the page's own
    origin and assert side-effects.

Playwright is intentionally lazy-loaded; if the library is missing the
browser tools degrade gracefully (every method raises a typed
:class:`BrowserUnavailable` so the LLM gets a recoverable error and the
agent can fall back to httpx). Tests use a minimal fake driver so the
suite runs without installing a real browser binary.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

log = logging.getLogger(__name__)


class BrowserUnavailable(RuntimeError):
    """Raised when Playwright (or a custom driver) can't be initialised."""


# ── Driver protocol ──────────────────────────────────────────────


class _PageDriver(Protocol):
    """Minimal surface the BrowserSession needs from a backend page object."""

    def goto(self, url: str) -> None: ...
    def click(self, selector: str) -> None: ...
    def fill(self, selector: str, value: str) -> None: ...
    def press(self, selector: str, key: str) -> None: ...
    def evaluate(self, expression: str) -> Any: ...
    def screenshot(self) -> bytes: ...
    def url(self) -> str: ...
    def content(self) -> str: ...
    def close(self) -> None: ...


class _BrowserDriver(Protocol):
    """Backend factory for new pages. Implementations: Playwright, fake."""

    def new_page(self) -> _PageDriver: ...
    def close(self) -> None: ...


# ── Page wrapper ────────────────────────────────────────────────


@dataclass
class PageHandle:
    """One open tab. Owned by :class:`BrowserSession`."""

    name: str
    driver: _PageDriver
    history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": safe_call(self.driver.url, default=""),
            "history": list(self.history),
        }


def safe_call(fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """Best-effort call — used to keep ``to_dict`` from raising mid-render."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — defensive serialisation
        log.debug("safe_call failed: %s", exc)
        return default


# ── Session ─────────────────────────────────────────────────────


class BrowserSession:
    """Multi-tab browser session driven by a pluggable backend.

    Tests pass a stub :class:`_BrowserDriver`; production wiring uses
    :func:`playwright_driver` which lazy-imports Playwright and starts
    a chromium instance.
    """

    def __init__(self, driver: _BrowserDriver) -> None:
        self._driver = driver
        self._pages: dict[str, PageHandle] = {}

    @classmethod
    def from_playwright(cls, *, headless: bool = True, browser: str = "chromium") -> BrowserSession:
        """Build a session backed by a real Playwright browser.

        Raises :class:`BrowserUnavailable` if the dependency is missing.
        """
        return cls(_make_playwright_driver(headless=headless, browser=browser))

    # ── tab management ──────────────────────────────────────────

    def open_page(self, name: str = "page") -> PageHandle:
        if not name:
            raise ValueError("page name is required")
        if name in self._pages:
            raise ValueError(f"page {name!r} already open; pick a unique name")
        page = self._driver.new_page()
        handle = PageHandle(name=name, driver=page)
        self._pages[name] = handle
        return handle

    def close_page(self, name: str) -> None:
        page = self._pages.pop(name, None)
        if page is None:
            return
        try:
            page.driver.close()
        except Exception as exc:  # noqa: BLE001 — best effort
            log.debug("close_page %s: %s", name, exc)

    def list_pages(self) -> list[str]:
        return list(self._pages.keys())

    def get(self, name: str) -> PageHandle:
        try:
            return self._pages[name]
        except KeyError:
            raise KeyError(f"no open page named {name!r}") from None

    # ── navigation + interaction ────────────────────────────────

    def navigate(self, name: str, url: str) -> str:
        page = self.get(name)
        page.driver.goto(url)
        page.history.append(url)
        return safe_call(page.driver.url, default=url)

    def current_url(self, name: str) -> str:
        return safe_call(self.get(name).driver.url, default="")

    def content(self, name: str) -> str:
        return safe_call(self.get(name).driver.content, default="")

    def click(self, name: str, selector: str) -> None:
        self.get(name).driver.click(selector)

    def fill(self, name: str, selector: str, value: str) -> None:
        self.get(name).driver.fill(selector, value)

    def press(self, name: str, selector: str, key: str) -> None:
        self.get(name).driver.press(selector, key)

    def evaluate(self, name: str, expression: str) -> Any:
        return self.get(name).driver.evaluate(expression)

    def screenshot(self, name: str) -> bytes:
        return self.get(name).driver.screenshot()

    # ── lifecycle ───────────────────────────────────────────────

    def close(self) -> None:
        for handle in list(self._pages.values()):
            try:
                handle.driver.close()
            except Exception as exc:  # noqa: BLE001
                log.debug("close failure for %s: %s", handle.name, exc)
        self._pages.clear()
        try:
            self._driver.close()
        except Exception as exc:  # noqa: BLE001
            log.debug("driver close failure: %s", exc)

    def __enter__(self) -> BrowserSession:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


# ── Playwright bridge (lazy) ────────────────────────────────────


def _make_playwright_driver(*, headless: bool, browser: str) -> _BrowserDriver:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — exercised in env-deps tests
        raise BrowserUnavailable(
            "Playwright is not installed. Install via "
            "``uv pip install playwright && playwright install chromium`` to enable "
            "browser automation."
        ) from exc
    if browser not in {"chromium", "firefox", "webkit"}:
        raise ValueError(f"unsupported browser {browser!r}")
    pw = sync_playwright().start()
    launcher = getattr(pw, browser)
    browser_obj = launcher.launch(headless=headless)
    context = browser_obj.new_context()

    class _PlaywrightPage:
        def __init__(self, page: Any) -> None:
            self._page = page

        def goto(self, url: str) -> None:
            self._page.goto(url)

        def click(self, selector: str) -> None:
            self._page.click(selector)

        def fill(self, selector: str, value: str) -> None:
            self._page.fill(selector, value)

        def press(self, selector: str, key: str) -> None:
            self._page.press(selector, key)

        def evaluate(self, expression: str) -> Any:
            return self._page.evaluate(expression)

        def screenshot(self) -> bytes:
            return self._page.screenshot()

        def url(self) -> str:
            return self._page.url

        def content(self) -> str:
            return self._page.content()

        def close(self) -> None:
            self._page.close()

    class _PlaywrightDriver:
        def new_page(self) -> _PageDriver:
            return _PlaywrightPage(context.new_page())

        def close(self) -> None:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser_obj.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass

    return _PlaywrightDriver()


@contextmanager
def playwright_session(
    *, headless: bool = True, browser: str = "chromium"
) -> Iterator[BrowserSession]:
    """Context-managed Playwright session for ad-hoc agent calls."""
    session = BrowserSession.from_playwright(headless=headless, browser=browser)
    try:
        yield session
    finally:
        session.close()


__all__ = [
    "BrowserSession",
    "BrowserUnavailable",
    "PageHandle",
    "playwright_session",
]
