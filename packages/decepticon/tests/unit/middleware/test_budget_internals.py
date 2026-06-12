"""Infra-free coverage for ``decepticon.middleware.budget`` internals.

``test_budget.py`` covers cache set/get/eviction and the ``_enforce``
threshold paths. This adds the remaining pure, DB-free logic that a
silent regression would slip through:

* ``_env_float`` — empty / whitespace / invalid / valid env parsing
  (a wrong fallback silently disables or mis-sizes the spend cap);
* ``_SpendCache`` **TTL expiry** — a stale entry that never expires would
  let spend drift unbounded between polls;
* ``_scope_keys`` — request-state + runtime extraction and the
  env / hard-coded-default fallback chain (wrong scope key = wrong cap);
* ``wrap_model_call`` / ``awrap_model_call`` — both delegate to the
  handler under cap and short-circuit (raise) *before* the handler runs
  once the cap is hit.

The spend source is injected, so there is no LiteLLM / Postgres dependency.
"""

from __future__ import annotations

import pytest

from decepticon.middleware import budget as budget_mod
from decepticon.middleware.budget import (
    BudgetEnforcementMiddleware,
    BudgetExceeded,
    _default_litellm_spend_provider,
    _emit_warning_event,
    _env_float,
    _SpendCache,
)

# ---------------------------------------------------------------- _env_float

_ENV = "DECEPTICON_BUDGET__TEST_CAP"


def test_env_float_unset_returns_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(_ENV, raising=False)
    assert _env_float(_ENV, 4.0) == 4.0


def test_env_float_blank_and_whitespace_return_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(_ENV, "   ")
    assert _env_float(_ENV, 2.5) == 2.5


def test_env_float_invalid_returns_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(_ENV, "not-a-number")
    assert _env_float(_ENV, 9.0) == 9.0


def test_env_float_valid_parses(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(_ENV, "12.5")
    assert _env_float(_ENV, 0.0) == 12.5


# ---------------------------------------------------------------- _SpendCache TTL


def test_spend_cache_entry_expires_after_ttl(monkeypatch: pytest.MonkeyPatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(budget_mod.time, "monotonic", lambda: clock["t"])
    cache = _SpendCache(ttl_seconds=5.0)
    cache.set("k", 3.0)

    clock["t"] = 1004.0  # still within ttl
    assert cache.get("k") == 3.0

    clock["t"] = 1006.0  # past ttl
    assert cache.get("k") is None
    assert "k" not in cache._entries  # expired entry is dropped, not just hidden


# ---------------------------------------------------------------- _scope_keys


class _Runtime:
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name


class _Req:
    def __init__(self, state: object = None, runtime: object = None) -> None:
        self.state = state
        self.runtime = runtime
        self.model_settings: dict[str, object] = {}

    def override(self, **kwargs: object) -> _Req:
        # mirrors langchain's ModelRequest.override: shallow copy + updates
        new = _Req(state=self.state, runtime=self.runtime)
        new.__dict__.update(self.__dict__)
        new.__dict__.update(kwargs)
        return new


def _mw() -> BudgetEnforcementMiddleware:
    return BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=5.0,
        spend_provider=lambda _k: 0.0,
    )


def test_scope_keys_reads_state_and_runtime():
    mw = _mw()
    req = _Req(state={"engagement_name": "eng-7"}, runtime=_Runtime("recon"))
    assert mw._scope_keys(req) == ("eng-7", "recon")


def test_scope_keys_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_ID", "env-eng")
    eng, agent = _mw()._scope_keys(_Req(state={}, runtime=None))
    assert eng == "env-eng"
    assert agent == "default-agent"


def test_scope_keys_ultimate_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DECEPTICON_ENGAGEMENT_ID", raising=False)
    eng, agent = _mw()._scope_keys(_Req(state=None, runtime=None))
    assert eng == "default-engagement"
    assert agent == "default-agent"


# ---------------------------------------------------------------- concurrency


def test_check_one_soft_warn_fires_once_under_concurrent_threads(
    monkeypatch: pytest.MonkeyPatch,
):
    """The _lock keeps the soft-warn invariant under the thread-pool path.

    awrap_model_call runs _enforce via asyncio.to_thread, so concurrent
    agents land in _check_one on different OS threads. Without the lock the
    check-then-add on _warned_scopes races and emits duplicate warnings; with
    it, exactly one fires per scope no matter how many threads pile in.
    """
    import threading

    emitted: list[tuple[str, float, float, float]] = []
    barrier = threading.Barrier(8)

    def provider(_k: str) -> float:
        return 8.0  # 80% of a 10.0 cap → over the 0.7 soft-warn threshold

    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        soft_warn_at_pct=0.7,
        spend_provider=provider,
    )

    # capture every emit instead of reaching into langgraph stream internals
    def fake_emit(scope: str, spent: float, cap: float, frac: float) -> None:
        emitted.append((scope, spent, cap, frac))

    monkeypatch.setattr(budget_mod, "_emit_warning_event", fake_emit)

    def worker() -> None:
        barrier.wait()  # maximize overlap on the check-then-add
        mw._check_one("engagement", "engagement:test", 10.0)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(emitted) == 1
    assert mw._warned_scopes == {"engagement:engagement:test"}


def test_check_one_concurrent_cold_cache_fetches_once():
    """A cold cache hit by N concurrent threads issues exactly one provider call."""
    import threading

    calls = {"n": 0}
    gate = threading.Event()
    barrier = threading.Barrier(6)

    def provider(_k: str) -> float:
        calls["n"] += 1
        gate.wait(timeout=2.0)  # hold the first fetcher so others pile up on the lock
        return 1.0

    mw = BudgetEnforcementMiddleware(engagement_cap_usd=100.0, spend_provider=provider)

    def worker() -> None:
        barrier.wait()
        mw._check_one("engagement", "engagement:test", 100.0)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join()

    assert calls["n"] == 1  # the lock collapsed 6 cold-cache calls into one fetch


# ---------------------------------------------------------------- wrap_model_call


def test_wrap_model_call_invokes_handler_under_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DECEPTICON_BUDGET__PER_AGENT_USD", raising=False)
    mw = BudgetEnforcementMiddleware(engagement_cap_usd=100.0, spend_provider=lambda _k: 1.0)
    called: dict[str, bool] = {}

    def handler(_req: object) -> str:
        called["ran"] = True
        return "RESULT"

    assert mw.wrap_model_call(_Req(state={}, runtime=None), handler) == "RESULT"
    assert called == {"ran": True}


def test_wrap_model_call_short_circuits_when_over_cap():
    mw = BudgetEnforcementMiddleware(engagement_cap_usd=10.0, spend_provider=lambda _k: 999.0)

    def handler(_req: object) -> str:
        raise AssertionError("handler must not run once the budget is exceeded")

    with pytest.raises(BudgetExceeded) as exc:
        mw.wrap_model_call(_Req(state={}, runtime=None), handler)
    assert exc.value.scope == "engagement"


async def test_awrap_model_call_invokes_handler_under_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DECEPTICON_BUDGET__PER_AGENT_USD", raising=False)
    mw = BudgetEnforcementMiddleware(engagement_cap_usd=100.0, spend_provider=lambda _k: 1.0)

    async def handler(_req: object) -> str:
        return "ASYNC_RESULT"

    assert await mw.awrap_model_call(_Req(state={}, runtime=None), handler) == "ASYNC_RESULT"


async def test_awrap_model_call_short_circuits_when_over_cap():
    mw = BudgetEnforcementMiddleware(engagement_cap_usd=10.0, spend_provider=lambda _k: 999.0)

    async def handler(_req: object) -> str:
        raise AssertionError("handler must not run once the budget is exceeded")

    with pytest.raises(BudgetExceeded):
        await mw.awrap_model_call(_Req(state={}, runtime=None), handler)


# ---------------------------------------------------------------- disabled passthrough
def test_disabled_middleware_is_passthrough(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DECEPTICON_BUDGET__ENGAGEMENT_USD", raising=False)
    monkeypatch.delenv("DECEPTICON_BUDGET__PER_AGENT_USD", raising=False)
    mw = BudgetEnforcementMiddleware()  # no caps -> disabled no-op

    def handler(_req: object) -> str:
        return "OK"

    assert mw.wrap_model_call(_Req(state={}, runtime=None), handler) == "OK"


# ---------------------------------------------------------------- _emit_warning_event
def test_emit_warning_event_writes_dashboard_contract(monkeypatch: pytest.MonkeyPatch):
    import langgraph.config as lgconfig

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        lgconfig,
        "get_stream_writer",
        lambda: lambda payload: captured.update(payload),
    )
    _emit_warning_event("engagement", 7.0, 10.0, 0.7)
    assert captured == {
        "type": "budget_warning",
        "scope": "engagement",
        "spent_usd": 7.0,
        "cap_usd": 10.0,
        "used_pct": 70.0,
    }


def test_emit_warning_event_noop_when_no_writer(monkeypatch: pytest.MonkeyPatch):
    import langgraph.config as lgconfig

    monkeypatch.setattr(lgconfig, "get_stream_writer", lambda: None)
    _emit_warning_event("agent", 1.0, 2.0, 0.5)  # must not raise


def test_emit_warning_event_swallows_writer_errors(monkeypatch: pytest.MonkeyPatch):
    import langgraph.config as lgconfig

    def _boom(_payload: object) -> None:
        raise RuntimeError("stream closed")

    monkeypatch.setattr(lgconfig, "get_stream_writer", lambda: _boom)
    _emit_warning_event("agent", 1.0, 2.0, 0.5)  # logged, not raised


# ---------------------------------------------------------------- default provider


class _StubResponse:
    def __init__(self, rows: list[dict[str, object]], status_error: bool = False) -> None:
        self._rows = rows
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error:
            raise RuntimeError("HTTP 500")

    def json(self) -> list[dict[str, object]]:
        return self._rows


class _StubLLMConfig:
    proxy_url = "http://litellm:4000/"
    proxy_api_key = "sk-test-master"


class _StubConfig:
    llm = _StubLLMConfig()


def _install_stub_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import decepticon_core.utils.config as core_config

    # _StubConfig is itself the callable load_config should become: load_config()
    # then constructs a fresh _StubConfig instance, matching the real signature.
    monkeypatch.setattr(core_config, "load_config", _StubConfig)


def test_default_provider_returns_matching_tag_spend(monkeypatch: pytest.MonkeyPatch):
    import httpx

    _install_stub_config(monkeypatch)
    captured: dict[str, object] = {}

    def _get(url: str, *, headers: dict[str, str], timeout: float) -> _StubResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _StubResponse(
            [
                {"individual_request_tag": "User-Agent: curl", "total_spend": 9.9},
                {"individual_request_tag": "engagement:test", "total_spend": 12.5},
            ]
        )

    monkeypatch.setattr(httpx, "get", _get)

    assert _default_litellm_spend_provider("engagement:test") == 12.5
    # trailing slash on proxy_url must not produce a double slash
    assert captured["url"] == "http://litellm:4000/spend/tags"
    assert captured["headers"] == {"Authorization": "Bearer sk-test-master"}


def test_default_provider_unknown_tag_returns_zero(monkeypatch: pytest.MonkeyPatch):
    import httpx

    _install_stub_config(monkeypatch)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_a, **_k: _StubResponse([{"individual_request_tag": "other", "total_spend": 3.0}]),
    )

    assert _default_litellm_spend_provider("engagement:test") == 0.0


def test_default_provider_swallows_http_errors(monkeypatch: pytest.MonkeyPatch):
    import httpx

    _install_stub_config(monkeypatch)
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _StubResponse([], status_error=True))

    assert _default_litellm_spend_provider("engagement:test") == 0.0


def test_default_provider_swallows_config_errors(monkeypatch: pytest.MonkeyPatch):
    import decepticon_core.utils.config as core_config

    def _boom() -> object:
        raise RuntimeError("no env")

    monkeypatch.setattr(core_config, "load_config", _boom)

    assert _default_litellm_spend_provider("engagement:test") == 0.0


def test_default_provider_null_total_spend_is_zero(monkeypatch: pytest.MonkeyPatch):
    import httpx

    _install_stub_config(monkeypatch)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_a, **_k: _StubResponse(
            [{"individual_request_tag": "engagement:test", "total_spend": None}]
        ),
    )

    assert _default_litellm_spend_provider("engagement:test") == 0.0
