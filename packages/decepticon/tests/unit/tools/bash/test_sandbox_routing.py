"""Per-engagement sandbox routing — the isolation property that lets one SHARED
langgraph process serve many engagements, each on its OWN sandbox.

``get_sandbox(config)`` resolves the sandbox from the run's injected
``configurable.sandbox_url`` (mirroring how ``_workspace_path_from_config``
resolves the workspace), so a tenant's bash can never reach another tenant's
sandbox. Without that key it falls back to the process-default sandbox, so
single-tenant / dev / OSS self-host behavior is unchanged.
"""

from unittest.mock import MagicMock

from decepticon.backends import factory
from decepticon.tools.bash.bash import get_sandbox, set_sandbox


def _cfg(url: str, token: str = "tok") -> dict:
    return {"configurable": {"sandbox_url": url, "sandbox_token": token}}


def setup_function() -> None:
    # Isolate the (url, token)-keyed client cache between tests.
    factory._shared_sandbox.cache_clear()


def test_resolves_distinct_sandbox_per_engagement_config() -> None:
    a = get_sandbox(_cfg("http://eng-a:9999"))
    b = get_sandbox(_cfg("http://eng-b:9999"))
    assert a is not None and b is not None
    assert a._base_url == "http://eng-a:9999"
    assert b._base_url == "http://eng-b:9999"
    assert a is not b  # no cross-tenant sharing
    # same engagement reuses the cached client (SandboxNotificationMiddleware
    # _jobs view must stay consistent within a run)
    assert get_sandbox(_cfg("http://eng-a:9999")) is a


def test_config_takes_precedence_over_process_default() -> None:
    default = MagicMock()
    set_sandbox(default)
    resolved = get_sandbox(_cfg("http://eng-x:9999"))
    assert resolved is not default
    assert resolved is not None and resolved._base_url == "http://eng-x:9999"


def test_falls_back_to_default_without_sandbox_url() -> None:
    default = MagicMock()
    set_sandbox(default)
    assert get_sandbox() is default
    assert get_sandbox({"configurable": {}}) is default
    assert get_sandbox({"configurable": {"sandbox_url": ""}}) is default
    # malformed configurable must not raise — fail safe to the default
    assert get_sandbox({"configurable": "not-a-dict"}) is default


def test_token_is_part_of_the_cache_key() -> None:
    # Same URL, different token → distinct clients (defence-in-depth: a rotated
    # per-engagement token must not reuse a stale-auth client).
    t1 = get_sandbox(_cfg("http://eng:9999", "tok-1"))
    t2 = get_sandbox(_cfg("http://eng:9999", "tok-2"))
    assert t1 is not t2


def test_subagent_override_wins_when_config_lacks_sandbox_url() -> None:
    """Sub-agent tools get a config WITHOUT ``sandbox_url`` (langgraph re-seeds
    its config contextvar per node), so bash fell back to the process default —
    the shared sidecar. StreamingRunnable._bind_per_run_sandbox sets the run's
    sandbox as the ``_sandbox_var`` override (which langgraph does NOT touch), so
    get_sandbox honours it before the default and the sub-agent reaches the VM.
    """
    from decepticon.tools.bash.bash import _sandbox_var

    override = MagicMock()
    token = set_sandbox(override)
    try:
        assert get_sandbox({"configurable": {}}) is override
        assert get_sandbox(None) is override
        # an explicit per-run config.sandbox_url still wins (orchestrator path)
        assert get_sandbox(_cfg("http://eng-x:9999")) is not override
    finally:
        _sandbox_var.reset(token)
