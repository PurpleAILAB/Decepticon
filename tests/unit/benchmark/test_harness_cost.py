"""Unit tests for Harness._query_cost — /spend/logs summation.

Kept in a separate file from test_harness.py so it doesn't inherit the
langgraph_sdk-coupled fixture mess that file is marked skipped over.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from benchmark.config import BenchmarkConfig
from benchmark.harness import Harness
from benchmark.providers.base import BaseBenchmarkProvider
from benchmark.schemas import Challenge, FilterConfig


class _StubProvider(BaseBenchmarkProvider):
    @property
    def name(self) -> str:  # pragma: no cover - trivial
        return "stub"

    def load_challenges(self, filters: FilterConfig) -> list[Challenge]:  # pragma: no cover
        return []

    def preflight_build(self, challenges: list[Challenge]) -> dict[str, str]:  # pragma: no cover
        return {}

    def setup(self, challenge: Challenge):  # type: ignore[override]  # pragma: no cover
        raise NotImplementedError

    def teardown(self, challenge: Challenge) -> None:  # pragma: no cover
        return None

    def evaluate(self, challenge: Challenge, state, workspace):  # pragma: no cover
        raise NotImplementedError


def _harness_with_mock(rows: Any, status: int = 200) -> Harness:
    config = BenchmarkConfig()
    provider = _StubProvider()
    h = Harness(provider, config)

    def handler(request: httpx.Request) -> httpx.Response:
        if status == 200:
            return httpx.Response(200, json=rows)
        return httpx.Response(status, text="upstream error")

    transport = httpx.MockTransport(handler)

    real_async_client = httpx.AsyncClient

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    # patch httpx.AsyncClient inside benchmark.harness module
    patcher = patch("benchmark.harness.httpx.AsyncClient", side_effect=patched)
    patcher.start()
    h._test_patcher = patcher  # type: ignore[attr-defined]
    return h


@pytest.mark.asyncio
async def test_query_cost_sums_spend_rows() -> None:
    rows = [
        {"spend": 0.01, "model": "anthropic/claude-haiku-4-5"},
        {"spend": 0.025, "model": "anthropic/claude-opus-4-7"},
        {"spend": 0.0, "model": "auth/claude-haiku-4-5"},
    ]
    h = _harness_with_mock(rows)
    try:
        total = await h._query_cost("2026-05-14T00:00:00Z", "2026-05-14T01:00:00Z")
    finally:
        h._test_patcher.stop()  # type: ignore[attr-defined]
    assert total == 0.035


@pytest.mark.asyncio
async def test_query_cost_returns_none_on_non_200() -> None:
    h = _harness_with_mock(None, status=500)
    try:
        total = await h._query_cost("a", "b")
    finally:
        h._test_patcher.stop()  # type: ignore[attr-defined]
    assert total is None


@pytest.mark.asyncio
async def test_query_cost_zero_when_no_rows() -> None:
    h = _harness_with_mock([])
    try:
        total = await h._query_cost("a", "b")
    finally:
        h._test_patcher.stop()  # type: ignore[attr-defined]
    assert total == 0.0


@pytest.mark.asyncio
async def test_query_cost_ignores_non_numeric_spend() -> None:
    rows = [
        {"spend": "not-a-number"},
        {"spend": None},
        {"spend": 0.7},
        {"not_a_spend_row": 1},
    ]
    h = _harness_with_mock(rows)
    try:
        total = await h._query_cost("a", "b")
    finally:
        h._test_patcher.stop()  # type: ignore[attr-defined]
    assert total == 0.7
