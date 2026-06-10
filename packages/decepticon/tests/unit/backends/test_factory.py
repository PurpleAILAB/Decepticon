"""Tests for ``decepticon.backends.factory.build_sandbox_backend``."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from decepticon.backends import build_sandbox_backend
from decepticon.backends.factory import _shared_sandbox


@pytest.fixture(autouse=True)
def _clear_shared_sandbox_cache() -> Iterator[None]:
    """The shared cache survives across the process, so isolate tests."""
    _shared_sandbox.cache_clear()
    yield
    _shared_sandbox.cache_clear()


def test_build_sandbox_backend_returns_shared_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated calls with the same env must return the *same* HTTPSandbox.

    Why this matters: ``langgraph dev`` invokes one factory per registered
    graph at startup. Without a shared instance every factory builds its
    own ``HTTPSandbox`` + ``BackgroundJobTracker``, and the
    ``SandboxNotificationMiddleware`` instance held by each graph sees a
    different ``_jobs`` view than the bash tool actually registers
    against — completion notifications never reach the agent.
    """
    monkeypatch.setenv("SAAS_SANDBOX_URL", "http://sandbox:9999")
    monkeypatch.delenv("SAAS_SANDBOX_TOKEN", raising=False)

    a = build_sandbox_backend()
    b = build_sandbox_backend()

    assert a is b
    assert a._jobs is b._jobs


def test_build_sandbox_backend_keys_on_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct base URLs must produce distinct instances.

    Multi-tenant SaaS pools may target different daemons in the same
    process; the cache key must respect that.
    """
    monkeypatch.setenv("SAAS_SANDBOX_URL", "http://sandbox-a:9999")
    monkeypatch.delenv("SAAS_SANDBOX_TOKEN", raising=False)
    a = build_sandbox_backend()

    monkeypatch.setenv("SAAS_SANDBOX_URL", "http://sandbox-b:9999")
    b = build_sandbox_backend()

    assert a is not b


def test_build_sandbox_backend_keys_on_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct tokens against the same URL still produce distinct instances."""
    monkeypatch.setenv("SAAS_SANDBOX_URL", "http://sandbox:9999")

    monkeypatch.setenv("SAAS_SANDBOX_TOKEN", "tenant-a")
    a = build_sandbox_backend()

    monkeypatch.setenv("SAAS_SANDBOX_TOKEN", "tenant-b")
    b = build_sandbox_backend()

    assert a is not b
