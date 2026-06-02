"""Defensive-wrap behavior for the SUMMARIZATION slot.

The summarization middleware issues a live LLM call inside the agent
loop; when its provider fails (timeout / 5xx / context-overflow retry
also failing) we must keep the surrounding agent run alive by skipping
that turn's summarization instead of bubbling the exception up. These
tests pin that contract via a fake inner middleware whose hook can be
flipped between "raises" and "returns normally".
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest

from decepticon.agents.middleware_slots import _SafeSummarizationProxy

# The ``decepticon`` parent logger is configured with ``propagate=False``
# (see decepticon_core.utils.logging), so caplog's root-attached handler
# never sees records emitted under it. We attach a dedicated handler
# directly to the proxy's logger to assert the warning is fired.
_PROXY_LOGGER = "decepticon.agents.middleware_slots"


@pytest.fixture
def warn_records() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []
    handler = logging.Handler(level=logging.WARNING)
    handler.emit = records.append  # type: ignore[method-assign]
    logger = logging.getLogger(_PROXY_LOGGER)
    prior = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior)


class _FakeInner:
    """Stand-in for the deepagents summarization middleware.

    Mirrors the public surface ``_SafeSummarizationProxy`` reads from
    the real inner (``state_schema``, ``tools``, ``name`` plus the two
    wrap-model-call hooks) without dragging the real LLM-bound class
    into the test.
    """

    state_schema = dict
    tools: list[Any] = []
    name = "FakeSummarizationInner"

    def __init__(self, *, fail: bool) -> None:
        self._fail = fail
        self.sync_calls = 0
        self.async_calls = 0

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        self.sync_calls += 1
        if self._fail:
            raise RuntimeError("summarization LLM exploded")
        return ("inner-sync", request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        self.async_calls += 1
        if self._fail:
            raise RuntimeError("summarization LLM exploded (async)")
        return ("inner-async", request)


def _handler(request: Any) -> Any:
    return ("handler", request)


async def _ahandler(request: Any) -> Any:
    return ("ahandler", request)


def test_sync_failure_falls_back_to_handler_and_logs(
    warn_records: list[logging.LogRecord],
) -> None:
    inner = _FakeInner(fail=True)
    proxy = _SafeSummarizationProxy(inner)

    result = proxy.wrap_model_call("REQ", _handler)

    assert result == ("handler", "REQ")
    assert inner.sync_calls == 1
    assert any(
        "summarization" in rec.getMessage().lower() and rec.levelno == logging.WARNING
        for rec in warn_records
    ), warn_records


def test_sync_success_passes_inner_result_through() -> None:
    inner = _FakeInner(fail=False)
    proxy = _SafeSummarizationProxy(inner)

    result = proxy.wrap_model_call("REQ", _handler)

    assert result == ("inner-sync", "REQ")
    assert inner.sync_calls == 1


@pytest.mark.asyncio
async def test_async_failure_falls_back_to_handler_and_logs(
    warn_records: list[logging.LogRecord],
) -> None:
    inner = _FakeInner(fail=True)
    proxy = _SafeSummarizationProxy(inner)

    result = await proxy.awrap_model_call("REQ", _ahandler)

    assert result == ("ahandler", "REQ")
    assert inner.async_calls == 1
    assert any(
        "summarization" in rec.getMessage().lower() and rec.levelno == logging.WARNING
        for rec in warn_records
    ), warn_records


@pytest.mark.asyncio
async def test_async_success_passes_inner_result_through() -> None:
    inner = _FakeInner(fail=False)
    proxy = _SafeSummarizationProxy(inner)

    result = await proxy.awrap_model_call("REQ", _ahandler)

    assert result == ("inner-async", "REQ")
    assert inner.async_calls == 1


def test_proxy_forwards_inner_state_schema_and_name() -> None:
    inner = _FakeInner(fail=False)
    proxy = _SafeSummarizationProxy(inner)

    # The factory inspects ``state_schema`` per-instance (langchain
    # collects ``m.state_schema for m in middleware``) and ``name`` for
    # tracing. Both must reflect the wrapped middleware so the inner's
    # state extensions and observability survive the wrap.
    assert proxy.state_schema is inner.state_schema
    assert proxy.name == inner.name
