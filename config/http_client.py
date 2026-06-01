"""Dual-stack-resilient HTTP wrappers for LiteLLM OAuth handlers.

OAuth handlers call provider APIs that publish both A and AAAA DNS records.
In environments without IPv6 routing (WSL2, Docker Desktop, corporate NAT),
sync httpx can surface ``ENETUNREACH`` from the first connect attempt before
the underlying socket iteration completes — observed as
``[Errno 101] Network is unreachable`` mid-stream in ``api.anthropic.com``
calls from the Claude Code subscription handler.

This module wraps httpx with built-in transport-level connect retries
(``HTTPTransport(retries=N)`` / ``AsyncHTTPTransport(retries=N)``) so that a
transient connect failure on one address family forces a full re-resolve and
re-iterate on the next attempt. anyio (httpx's async backend) already
implements RFC 8305 Happy Eyeballs (default delay 0.25s); we keep dual-stack
DNS behavior intact and only add a defensive retry layer on top.

API (drop-in for httpx counterparts):
    post(url, **kwargs)        → ``httpx.post`` with connect retries
    async_post(url, **kwargs)  → ``await httpx.AsyncClient().post`` equivalent
    sync_client(**kwargs)      → ``httpx.Client`` context manager
    async_client(**kwargs)     → ``httpx.AsyncClient`` context manager

Module import has no side effects.
"""

from __future__ import annotations

from typing import Any

import httpx

# Transport-level connect retries. 3 attempts ≈ tolerates a transient
# ENETUNREACH on a misconfigured dual-stack while still failing fast on a
# genuine outage (each retry re-resolves via getaddrinfo, picking up whatever
# the kernel currently considers reachable).
_CONNECT_RETRIES = 3


def sync_client(**kwargs: Any) -> httpx.Client:
    """Construct an ``httpx.Client`` with connect-retry resilience.

    Caller-supplied ``transport`` overrides the default retrying transport.
    All other kwargs are forwarded to ``httpx.Client`` verbatim.
    """
    transport = kwargs.pop("transport", None) or httpx.HTTPTransport(retries=_CONNECT_RETRIES)
    return httpx.Client(transport=transport, **kwargs)


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Construct an ``httpx.AsyncClient`` with connect-retry resilience."""
    transport = kwargs.pop("transport", None) or httpx.AsyncHTTPTransport(retries=_CONNECT_RETRIES)
    return httpx.AsyncClient(transport=transport, **kwargs)


def post(url: str, **kwargs: Any) -> httpx.Response:
    """Connect-retry-resilient drop-in for ``httpx.post``.

    Use exactly like ``httpx.post(url, ...)``. A dedicated short-lived
    client is constructed per call to mirror ``httpx.post``'s contract;
    callers that need keep-alive should use ``sync_client()`` instead.
    """
    with sync_client() as client:
        return client.post(url, **kwargs)


async def async_post(url: str, **kwargs: Any) -> httpx.Response:
    """Connect-retry-resilient drop-in for an async ``httpx`` POST."""
    async with async_client() as client:
        return await client.post(url, **kwargs)
