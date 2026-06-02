"""Per-request timeout override + exception safety on HTTPSession.request."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from decepticon.tools.web.http import HTTPSession


class TestHTTPSessionPerRequestTimeout:
    async def test_timeout_ms_is_forwarded_to_underlying_client_request(self) -> None:
        session = HTTPSession()
        try:
            captured: dict[str, Any] = {}

            async def fake_request(**kwargs: Any) -> httpx.Response:
                captured.update(kwargs)
                return httpx.Response(200, content=b"ok")

            session._client.request = fake_request  # type: ignore[method-assign]
            await session.request("GET", "https://x.test/ep", timeout_ms=2500)
            assert "timeout" in captured
            assert captured["timeout"] == pytest.approx(2.5)
        finally:
            await session.close()

    async def test_timeout_unset_does_not_pass_timeout_kwarg(self) -> None:
        session = HTTPSession()
        try:
            captured: dict[str, Any] = {}

            async def fake_request(**kwargs: Any) -> httpx.Response:
                captured.update(kwargs)
                return httpx.Response(200, content=b"ok")

            session._client.request = fake_request  # type: ignore[method-assign]
            await session.request("GET", "https://x.test/ep")
            assert "timeout" not in captured
        finally:
            await session.close()

    async def test_timeout_zero_is_forwarded_not_treated_as_unset(self) -> None:
        session = HTTPSession()
        try:
            captured: dict[str, Any] = {}

            async def fake_request(**kwargs: Any) -> httpx.Response:
                captured.update(kwargs)
                return httpx.Response(200, content=b"ok")

            session._client.request = fake_request  # type: ignore[method-assign]
            await session.request("GET", "https://x.test/ep", timeout_ms=0)
            assert "timeout" in captured
            assert captured["timeout"] == pytest.approx(0.0)
        finally:
            await session.close()

    async def test_response_is_closed_when_history_record_raises(self) -> None:
        session = HTTPSession()
        try:
            fake_resp = MagicMock(spec=httpx.Response)
            fake_resp.status_code = 200
            fake_resp.headers = {}
            fake_resp.content = b"ok"
            fake_resp.aclose = AsyncMock()

            async def fake_request(**_kwargs: Any) -> httpx.Response:
                return fake_resp

            session._client.request = fake_request  # type: ignore[method-assign]
            with patch.object(session.history, "record", side_effect=RuntimeError("boom")):
                with pytest.raises(RuntimeError, match="boom"):
                    await session.request("GET", "https://x.test/ep")
            fake_resp.aclose.assert_awaited_once()
        finally:
            await session.close()
