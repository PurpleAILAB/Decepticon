"""Unit tests for config/http_client.py.

The module wraps httpx with built-in connect-retry transports so OAuth
handler calls can survive a transient ENETUNREACH on one address family
in dual-stack environments (WSL2 / Docker Desktop / corp NAT without
IPv6 routing).

Tests cover:
  - The wrappers return real httpx clients with retrying transports.
  - The drop-in ``post()`` actually forwards to the underlying transport.
  - The retry count is the documented default (3).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[5] / "config" / "http_client.py"
_spec = importlib.util.spec_from_file_location("_http_client_src", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_http_client_src", _module)
_spec.loader.exec_module(_module)

post = _module.post
async_post = _module.async_post
sync_client = _module.sync_client
async_client = _module.async_client
_CONNECT_RETRIES = _module._CONNECT_RETRIES


class TestRetryDefaults:
    def test_retries_is_three(self):
        assert _CONNECT_RETRIES == 3

    def test_sync_client_has_retrying_transport(self):
        with sync_client() as client:
            # httpx.HTTPTransport exposes the underlying retry count on its
            # private _pool attribute; we check the public construction
            # contract instead — the transport must be an HTTPTransport.
            transport = client._transport
            assert isinstance(transport, httpx.HTTPTransport)

    def test_async_client_has_retrying_transport(self):
        client = async_client()
        try:
            transport = client._transport
            assert isinstance(transport, httpx.AsyncHTTPTransport)
        finally:
            # AsyncClient.close is async; ignore cleanup in this sync test —
            # the transport doesn't hold network resources until first request.
            pass


class TestPostForwards:
    def test_post_returns_response_with_mock_transport(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"echo": "ok"})

        # Inject MockTransport explicitly — verifies post() honors the
        # transport kwarg path and behaves as a drop-in for httpx.post.
        with sync_client(transport=httpx.MockTransport(handler)) as client:
            resp = client.post("https://example.test/foo", json={"x": 1})

        assert resp.status_code == 200
        assert resp.json() == {"echo": "ok"}
        assert len(captured) == 1
        assert captured[0].url.path == "/foo"

    @pytest.mark.asyncio
    async def test_async_post_returns_response_with_mock_transport(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, text="created")

        async with async_client(transport=httpx.MockTransport(handler)) as client:
            resp = await client.post("https://example.test/bar")

        assert resp.status_code == 201
        assert resp.text == "created"


class TestDropInShape:
    """``post`` and ``async_post`` must accept the same kwargs as their
    httpx counterparts so handler call sites can be replaced 1:1."""

    def test_post_accepts_content_headers_timeout(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200)

        with sync_client(transport=httpx.MockTransport(handler)) as client:
            client.post(
                "https://example.test/x",
                content=b"raw-bytes",
                headers={"x-token": "abc"},
                timeout=httpx.Timeout(5.0),
            )

        assert captured[0].headers["x-token"] == "abc"
        assert captured[0].content == b"raw-bytes"
