"""Tests for bounded, logged cleanup in ``decepticon.tools.browser.tools``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from decepticon.tools.browser.tools import (
    BrowserSessionManager,
    _reset_session_manager_for_tests,
    _safe_close,
)

_LOGGER_NAME = "decepticon.tools.browser.tools"


@pytest.fixture(autouse=True)
def _reset_singleton() -> Iterator[None]:
    _reset_session_manager_for_tests()
    yield
    _reset_session_manager_for_tests()


@pytest.fixture(autouse=True)
def _propagate_decepticon_logger() -> Iterator[None]:
    # decepticon_core.utils.logging sets propagate=False on the "decepticon"
    # root, which blocks pytest's caplog. Restore propagation per test.
    parent = logging.getLogger("decepticon")
    prior = parent.propagate
    parent.propagate = True
    try:
        yield
    finally:
        parent.propagate = prior


@pytest.mark.asyncio
async def test_safe_close_logs_raised_exception(caplog: pytest.LogCaptureFixture) -> None:
    obj = MagicMock()

    async def boom() -> None:
        raise RuntimeError("close kaboom")

    obj.close = boom

    caplog.set_level(logging.DEBUG)
    logging.getLogger(_LOGGER_NAME).propagate = True
    await _safe_close(obj, "page", timeout=1.0)

    assert "page" in caplog.text and "close kaboom" in caplog.text, caplog.text


@pytest.mark.asyncio
async def test_safe_close_bounded_by_timeout(caplog: pytest.LogCaptureFixture) -> None:
    obj = MagicMock()

    async def hang() -> None:
        await asyncio.sleep(60)

    obj.close = hang

    caplog.set_level(logging.DEBUG)
    logging.getLogger(_LOGGER_NAME).propagate = True
    loop = asyncio.get_running_loop()
    start = loop.time()
    await _safe_close(obj, "browser", timeout=0.05)
    elapsed = loop.time() - start

    assert elapsed < 5.0, f"hang was not bounded by timeout: {elapsed}s"
    assert "browser" in caplog.text and "timed out" in caplog.text.lower(), caplog.text


@pytest.mark.asyncio
async def test_close_continues_when_page_close_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mgr = BrowserSessionManager()

    bad_page = MagicMock()

    async def page_boom() -> None:
        raise RuntimeError("page broke")

    bad_page.close = page_boom

    context_closed = False
    browser_closed = False
    playwright_stopped = False

    async def ctx_close() -> None:
        nonlocal context_closed
        context_closed = True

    async def br_close() -> None:
        nonlocal browser_closed
        browser_closed = True

    async def pw_stop() -> None:
        nonlocal playwright_stopped
        playwright_stopped = True

    ctx = MagicMock()
    ctx.close = ctx_close
    br = MagicMock()
    br.close = br_close
    pw = MagicMock()
    pw.stop = pw_stop

    from decepticon.tools.browser.tools import _Tab

    mgr._tabs["main"] = _Tab(page=bad_page)
    mgr._active = "main"
    mgr._context = ctx
    mgr._browser = br
    mgr._playwright = pw

    caplog.set_level(logging.DEBUG)
    logging.getLogger(_LOGGER_NAME).propagate = True
    result = await mgr.close()

    assert result == {"closed": True}
    assert context_closed and browser_closed and playwright_stopped
    assert mgr._tabs == {}
    assert mgr._context is None
    assert mgr._browser is None
    assert mgr._playwright is None
    assert "page broke" in caplog.text, caplog.text


@pytest.mark.asyncio
async def test_close_bounded_when_browser_close_hangs() -> None:
    mgr = BrowserSessionManager()

    async def hang() -> None:
        await asyncio.sleep(60)

    br = MagicMock()
    br.close = hang
    pw = MagicMock()

    async def pw_stop() -> None:
        return None

    pw.stop = pw_stop
    mgr._browser = br
    mgr._playwright = pw

    loop = asyncio.get_running_loop()
    start = loop.time()
    # Wrap in our own outer timeout so a regression cannot wedge the test run.
    await asyncio.wait_for(mgr.close(), timeout=10.0)
    elapsed = loop.time() - start
    assert elapsed < 8.0, f"close did not bound hung browser.close(): {elapsed}s"
    assert mgr._browser is None
    assert mgr._playwright is None
