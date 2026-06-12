"""Tests for decepticon.middleware.budget."""

from __future__ import annotations

import pytest

from decepticon.middleware.budget import (
    BudgetEnforcementMiddleware,
    BudgetExceeded,
    _SpendCache,
)


def test_spend_cache_set_get():
    cache = _SpendCache(ttl_seconds=60.0)
    cache.set("k1", 1.23)
    assert cache.get("k1") == 1.23


def test_spend_cache_miss():
    cache = _SpendCache(ttl_seconds=60.0)
    assert cache.get("nope") is None


def test_spend_cache_eviction_at_capacity():
    cache = _SpendCache(ttl_seconds=60.0)
    for i in range(cache._MAX_ENTRIES + 10):
        cache.set(f"k{i}", float(i))
    assert len(cache._entries) <= cache._MAX_ENTRIES


def test_disabled_when_no_caps_set():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=0.0,
        per_agent_cap_usd=0.0,
        spend_provider=lambda _k: 1000.0,
    )
    assert mw._enabled() is False


def test_under_cap_does_not_raise():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        soft_warn_at_pct=0.7,
        spend_provider=lambda _k: 5.0,
    )

    class _Req:
        state = {"engagement_name": "test"}
        runtime = None

    mw._enforce(_Req())


def test_over_cap_raises_budget_exceeded():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        spend_provider=lambda _k: 15.0,
    )

    class _Req:
        state = {"engagement_name": "test"}
        runtime = None

    with pytest.raises(BudgetExceeded) as exc_info:
        mw._enforce(_Req())
    assert exc_info.value.scope == "engagement"
    assert exc_info.value.cap_usd == 10.0


def test_per_agent_cap_is_checked_separately():
    spends = {"engagement:test": 1.0, "agent:test:recon": 50.0}
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=100.0,
        per_agent_cap_usd=10.0,
        spend_provider=spends.get,
    )

    class _RT:
        agent_name = "recon"

    class _Req:
        state = {"engagement_name": "test"}
        runtime = _RT()

    with pytest.raises(BudgetExceeded) as exc_info:
        mw._enforce(_Req())
    assert exc_info.value.scope == "agent"


def test_provider_exception_is_swallowed():
    def _bad_provider(_k):
        raise RuntimeError("postgres down")

    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        spend_provider=_bad_provider,
    )

    class _Req:
        state = {"engagement_name": "test"}
        runtime = None

    mw._enforce(_Req())


def test_soft_warn_fires_once_per_scope():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        soft_warn_at_pct=0.5,
        spend_provider=lambda _k: 7.0,
    )

    class _Req:
        state = {"engagement_name": "test"}
        runtime = None

    mw._enforce(_Req())
    assert "engagement:engagement:test" in mw._warned_scopes
    mw._enforce(_Req())
    assert len(mw._warned_scopes) == 1


# ------------------------------------------------------------- _tag_request


class _OverridableReq:
    """Minimal ModelRequest stand-in supporting ``override``."""

    def __init__(self, model_settings: dict | None = None):
        self.state = {"engagement_name": "test"}

        class _RT:
            agent_name = "recon"

        self.runtime = _RT()
        self.model_settings = model_settings or {}

    def override(self, **kwargs):
        new = _OverridableReq()
        new.__dict__.update(self.__dict__)
        new.__dict__.update(kwargs)
        return new


def test_tag_request_injects_scope_tags():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        spend_provider=lambda _k: 0.0,
    )
    tagged = mw._tag_request(_OverridableReq())
    tags = tagged.model_settings["extra_body"]["metadata"]["tags"]
    assert tags == ["engagement:test", "agent:test:recon"]


def test_tag_request_preserves_existing_extra_body_and_tags():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        spend_provider=lambda _k: 0.0,
    )
    req = _OverridableReq(
        model_settings={
            "extra_body": {
                "thinking": {"type": "enabled"},
                "metadata": {"tags": ["custom-tag"], "trace_id": "t-1"},
            },
            "max_tokens": 64,
        }
    )
    tagged = mw._tag_request(req)
    extra = tagged.model_settings["extra_body"]
    assert extra["thinking"] == {"type": "enabled"}
    assert tagged.model_settings["max_tokens"] == 64
    assert extra["metadata"]["trace_id"] == "t-1"
    assert extra["metadata"]["tags"] == [
        "custom-tag",
        "engagement:test",
        "agent:test:recon",
    ]
    # the original request's settings must not be mutated in place
    assert req.model_settings["extra_body"]["metadata"]["tags"] == ["custom-tag"]


def test_tag_request_is_idempotent():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=10.0,
        per_agent_cap_usd=0.0,
        spend_provider=lambda _k: 0.0,
    )
    once = mw._tag_request(_OverridableReq())
    twice = mw._tag_request(once)
    tags = twice.model_settings["extra_body"]["metadata"]["tags"]
    assert tags == ["engagement:test", "agent:test:recon"]


def test_tag_request_noop_when_disabled():
    mw = BudgetEnforcementMiddleware(
        engagement_cap_usd=0.0,
        per_agent_cap_usd=0.0,
        spend_provider=lambda _k: 0.0,
    )
    req = _OverridableReq()
    assert mw._tag_request(req) is req
