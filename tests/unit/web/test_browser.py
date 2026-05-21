"""Tests for the browser automation session (stub-driver path)."""

from __future__ import annotations

from typing import Any

import pytest

from decepticon.tools.web.browser import (
    BrowserSession,
    BrowserUnavailable,
    PageHandle,
)

# ── stub backend ─────────────────────────────────────────────────


class _FakePage:
    """Minimal page driver for tests — records every interaction."""

    def __init__(self) -> None:
        self._url = "about:blank"
        self._content = "<html></html>"
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.eval_results: dict[str, Any] = {}

    def goto(self, url: str) -> None:
        self.calls.append(("goto", (url,)))
        self._url = url

    def click(self, selector: str) -> None:
        self.calls.append(("click", (selector,)))

    def fill(self, selector: str, value: str) -> None:
        self.calls.append(("fill", (selector, value)))

    def press(self, selector: str, key: str) -> None:
        self.calls.append(("press", (selector, key)))

    def evaluate(self, expression: str) -> Any:
        self.calls.append(("evaluate", (expression,)))
        return self.eval_results.get(expression, None)

    def screenshot(self) -> bytes:
        self.calls.append(("screenshot", ()))
        return b"\x89PNG\r\n\x1a\n"

    def url(self) -> str:
        return self._url

    def content(self) -> str:
        return self._content

    def close(self) -> None:
        self.calls.append(("close", ()))


class _FakeDriver:
    def __init__(self) -> None:
        self.pages: list[_FakePage] = []
        self.closed = False

    def new_page(self) -> _FakePage:
        p = _FakePage()
        self.pages.append(p)
        return p

    def close(self) -> None:
        self.closed = True


# ── tab management ──────────────────────────────────────────────


def test_open_page_creates_handle():
    sess = BrowserSession(_FakeDriver())
    handle = sess.open_page("home")
    assert isinstance(handle, PageHandle)
    assert handle.name == "home"
    assert sess.list_pages() == ["home"]


def test_open_page_rejects_blank_name():
    sess = BrowserSession(_FakeDriver())
    with pytest.raises(ValueError, match="page name is required"):
        sess.open_page("")


def test_open_page_rejects_duplicate_name():
    sess = BrowserSession(_FakeDriver())
    sess.open_page("a")
    with pytest.raises(ValueError, match="already open"):
        sess.open_page("a")


def test_close_page_removes_from_session():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    sess.open_page("a")
    sess.close_page("a")
    assert sess.list_pages() == []
    # Underlying page received close()
    assert any(call[0] == "close" for call in driver.pages[0].calls)


def test_close_unknown_page_is_noop():
    sess = BrowserSession(_FakeDriver())
    sess.close_page("missing")  # no raise


def test_get_unknown_page_raises():
    sess = BrowserSession(_FakeDriver())
    with pytest.raises(KeyError):
        sess.get("nope")


def test_multiple_tabs():
    sess = BrowserSession(_FakeDriver())
    sess.open_page("a")
    sess.open_page("b")
    sess.open_page("c")
    assert sess.list_pages() == ["a", "b", "c"]


# ── navigation ──────────────────────────────────────────────────


def test_navigate_records_history():
    sess = BrowserSession(_FakeDriver())
    sess.open_page("p")
    sess.navigate("p", "https://example.com")
    sess.navigate("p", "https://example.com/login")
    assert sess.get("p").history == ["https://example.com", "https://example.com/login"]


def test_current_url_reflects_last_goto():
    sess = BrowserSession(_FakeDriver())
    sess.open_page("p")
    sess.navigate("p", "https://x.com")
    assert sess.current_url("p") == "https://x.com"


def test_content_returns_html():
    sess = BrowserSession(_FakeDriver())
    sess.open_page("p")
    assert "<html>" in sess.content("p")


# ── interaction ─────────────────────────────────────────────────


def test_click_proxies_to_driver():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    sess.open_page("p")
    sess.click("p", "button#submit")
    assert ("click", ("button#submit",)) in driver.pages[0].calls


def test_fill_proxies_to_driver():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    sess.open_page("p")
    sess.fill("p", "input[name=email]", "test@example.com")
    assert ("fill", ("input[name=email]", "test@example.com")) in driver.pages[0].calls


def test_press_proxies_to_driver():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    sess.open_page("p")
    sess.press("p", "input", "Enter")
    assert ("press", ("input", "Enter")) in driver.pages[0].calls


def test_evaluate_returns_driver_value():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    handle = sess.open_page("p")
    handle.driver.eval_results["document.title"] = "Login"  # type: ignore[attr-defined]
    assert sess.evaluate("p", "document.title") == "Login"


def test_screenshot_returns_bytes():
    sess = BrowserSession(_FakeDriver())
    sess.open_page("p")
    blob = sess.screenshot("p")
    assert blob.startswith(b"\x89PNG")


# ── lifecycle ───────────────────────────────────────────────────


def test_close_session_clears_pages_and_driver():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    sess.open_page("a")
    sess.open_page("b")
    sess.close()
    assert sess.list_pages() == []
    assert driver.closed is True


def test_session_context_manager_closes_on_exit():
    driver = _FakeDriver()
    with BrowserSession(driver) as sess:
        sess.open_page("a")
    assert driver.closed is True


def test_page_handle_to_dict_includes_history_and_url():
    driver = _FakeDriver()
    sess = BrowserSession(driver)
    sess.open_page("a")
    sess.navigate("a", "https://x")
    info = sess.get("a").to_dict()
    assert info["name"] == "a"
    assert info["url"] == "https://x"
    assert info["history"] == ["https://x"]


# ── playwright unavailability ──────────────────────────────────


def test_from_playwright_raises_when_dependency_missing(monkeypatch):
    """If Playwright isn't importable, the constructor surfaces a typed error."""
    import importlib
    import sys

    # Pretend the module is not installed by inserting a sentinel that
    # raises ImportError on submodule access.
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    importlib.invalidate_caches()
    with pytest.raises(BrowserUnavailable, match="Playwright is not installed"):
        BrowserSession.from_playwright()
