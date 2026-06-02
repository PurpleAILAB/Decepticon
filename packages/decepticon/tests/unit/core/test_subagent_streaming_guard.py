"""Consecutive-failure terminal guard for ``StreamingRunnable``.

Returning a generic per-failure error state (instead of re-raising) is
required to avoid PatchToolCallsMiddleware's "cancelled" loop. But the
orchestrator has no way to distinguish a transient subagent error from
one that will never succeed, so it just keeps re-delegating. This test
suite locks in a terminal signal: after
``MAX_SUBAGENT_CONSECUTIVE_FAILURES`` back-to-back failures, the wrapper
must surface a *distinct* terminal marker on the returned state, and a
successful run in between must reset the counter.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from decepticon.core.subagent_streaming import (
    MAX_SUBAGENT_CONSECUTIVE_FAILURES,
    StreamingRunnable,
    clear_subagent_renderer,
    set_subagent_renderer,
)

TERMINAL_MARKER = "[TERMINAL]"


class _ToggleRunnable(Runnable):
    """Inner runnable whose stream/astream raises or yields a final state
    based on the mutable ``should_fail`` flag — used to drive the
    failure counter across success transitions without swapping the
    pydantic-bound inner runnable on the wrapper."""

    _FINAL: dict[str, Any] = {"messages": [AIMessage(content="ok")]}

    def __init__(self, should_fail: bool = True) -> None:
        self.should_fail = should_fail
        self._exc = RuntimeError("boom")

    def stream(self, input: Any, config: Any = None, stream_mode: str = "values", **kwargs: Any):
        if self.should_fail:
            raise self._exc
        yield self._FINAL

    async def astream(
        self, input: Any, config: Any = None, stream_mode: str = "values", **kwargs: Any
    ):
        if self.should_fail:
            raise self._exc
        yield self._FINAL

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:  # pragma: no cover
        if self.should_fail:
            raise self._exc
        return self._FINAL

    async def ainvoke(
        self, input: Any, config: Any = None, **kwargs: Any
    ) -> Any:  # pragma: no cover
        if self.should_fail:
            raise self._exc
        return self._FINAL


class _Renderer:
    def on_subagent_start(self, *a: Any, **kw: Any) -> None: ...
    def on_subagent_end(self, *a: Any, **kw: Any) -> None: ...
    def on_subagent_message(self, *a: Any, **kw: Any) -> None: ...
    def on_subagent_tool_call(self, *a: Any, **kw: Any) -> None: ...  # pragma: no cover
    def on_subagent_tool_result(self, *a: Any, **kw: Any) -> None: ...  # pragma: no cover


@pytest.fixture
def renderer():
    token = set_subagent_renderer(_Renderer())
    try:
        yield
    finally:
        clear_subagent_renderer(token)


def _last_text(state: Any) -> str:
    return str(state["messages"][-1].content)


def _hm() -> dict[str, Any]:
    return {"messages": [HumanMessage(content="go")]}


class TestSyncTerminalGuard:
    def test_constant_is_positive(self) -> None:
        assert MAX_SUBAGENT_CONSECUTIVE_FAILURES >= 1

    def test_each_failure_before_cap_is_generic(self, renderer: None) -> None:
        wrapper = StreamingRunnable(_ToggleRunnable(), "scanner")
        for _ in range(MAX_SUBAGENT_CONSECUTIVE_FAILURES - 1):
            out = wrapper.invoke(_hm())
            text = _last_text(out)
            assert "failed" in text
            assert TERMINAL_MARKER not in text

    def test_failure_at_cap_emits_terminal_marker(self, renderer: None) -> None:
        wrapper = StreamingRunnable(_ToggleRunnable(), "scanner")
        out: Any = None
        for _ in range(MAX_SUBAGENT_CONSECUTIVE_FAILURES):
            out = wrapper.invoke(_hm())
        text = _last_text(out)
        assert TERMINAL_MARKER in text
        assert "scanner" in text
        assert str(MAX_SUBAGENT_CONSECUTIVE_FAILURES) in text

    def test_success_resets_counter(self, renderer: None) -> None:
        toggle = _ToggleRunnable(should_fail=True)
        wrapper = StreamingRunnable(toggle, "scanner")
        for _ in range(MAX_SUBAGENT_CONSECUTIVE_FAILURES - 1):
            wrapper.invoke(_hm())
        toggle.should_fail = False
        ok = wrapper.invoke(_hm())
        assert TERMINAL_MARKER not in _last_text(ok)
        toggle.should_fail = True
        out = wrapper.invoke(_hm())
        assert TERMINAL_MARKER not in _last_text(out)


@pytest.mark.asyncio
class TestAsyncTerminalGuard:
    async def test_failure_at_cap_emits_terminal_marker(self, renderer: None) -> None:
        wrapper = StreamingRunnable(_ToggleRunnable(), "verifier")
        out: Any = None
        for _ in range(MAX_SUBAGENT_CONSECUTIVE_FAILURES):
            out = await wrapper.ainvoke(_hm())
        text = _last_text(out)
        assert TERMINAL_MARKER in text
        assert "verifier" in text

    async def test_async_success_resets_counter(self, renderer: None) -> None:
        toggle = _ToggleRunnable(should_fail=True)
        wrapper = StreamingRunnable(toggle, "verifier")
        for _ in range(MAX_SUBAGENT_CONSECUTIVE_FAILURES - 1):
            await wrapper.ainvoke(_hm())
        toggle.should_fail = False
        ok = await wrapper.ainvoke(_hm())
        assert TERMINAL_MARKER not in _last_text(ok)
        toggle.should_fail = True
        out = await wrapper.ainvoke(_hm())
        assert TERMINAL_MARKER not in _last_text(out)
