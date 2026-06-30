"""Tests for ProxyKeyOverrideMiddleware.

The middleware re-binds the agent's LLM to a per-run LiteLLM virtual key
(threaded by the SaaS launch flow as ``config.configurable.proxy_api_key``) so
that, in a shared multi-tenant langgraph, each engagement's spend authenticates
with — and is therefore attributed to — that org's key/team instead of the env
master key. No key threaded ⇒ no-op (OSS / single-tenant unaffected).
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_openai import ChatOpenAI

from decepticon.middleware.proxy_key_override import (
    ProxyKeyOverrideMiddleware,
    _read_proxy_key,
    _rekey_model,
)


@pytest.fixture
def proxy_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env = {
        "DECEPTICON_LLM__PROXY_URL": "http://litellm:4000",
        "DECEPTICON_LLM__PROXY_API_KEY": "sk-decepticon-master",
        "DECEPTICON_LLM__TIMEOUT": "120",
        "DECEPTICON_LLM__MAX_RETRIES": "2",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


def _original_chat_model(
    model: str = "openai/gpt-5.5", temperature: float | None = 0.4
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key="sk-decepticon-master",
        base_url="http://litellm:4000",
    )


# ── _read_proxy_key ─────────────────────────────────────────────────────


class TestReadProxyKey:
    def test_runtime_context_takes_priority(self) -> None:
        class _Runtime:
            context = {"proxy_api_key": "sk-org-A"}

        class _Req:
            runtime = _Runtime()
            state = {"proxy_api_key": "sk-org-B"}

        assert _read_proxy_key(_Req()) == "sk-org-A"

    def test_state_used_when_runtime_absent(self) -> None:
        class _Req:
            runtime = None
            state = {"proxy_api_key": "sk-org-B"}

        assert _read_proxy_key(_Req()) == "sk-org-B"

    def test_empty_means_no_key(self) -> None:
        class _Runtime:
            context = {"proxy_api_key": "   "}

        class _Req:
            runtime = _Runtime()
            state: dict[str, Any] = {}

        assert _read_proxy_key(_Req()) == ""


# ── _rekey_model ────────────────────────────────────────────────────────


class TestRekeyModel:
    def test_swaps_api_key_to_per_run_key(self, proxy_env: dict[str, str]) -> None:
        bound = _rekey_model(_original_chat_model(), "sk-engagement-xyz")
        # The whole point: authenticate with the per-run key, NOT the master.
        assert bound.openai_api_key.get_secret_value() == "sk-engagement-xyz"
        assert bound.openai_api_key.get_secret_value() != proxy_env["DECEPTICON_LLM__PROXY_API_KEY"]

    def test_preserves_model_id_and_proxy_url(self, proxy_env: dict[str, str]) -> None:
        bound = _rekey_model(_original_chat_model(model="anthropic/claude-sonnet-4-6"), "sk-k")
        assert bound.model_name == "anthropic/claude-sonnet-4-6"
        assert bound.openai_api_base == proxy_env["DECEPTICON_LLM__PROXY_URL"]

    def test_drops_temperature_for_opus_4x(self, proxy_env: dict[str, str]) -> None:
        bound = _rekey_model(
            _original_chat_model(model="auth/claude-opus-4-8", temperature=0.4),
            "sk-k",
        )
        assert bound.temperature is None

    def test_preserves_temperature_for_other_models(self, proxy_env: dict[str, str]) -> None:
        bound = _rekey_model(_original_chat_model(temperature=0.4), "sk-k")
        assert bound.temperature == 0.4


# ── Middleware wiring ───────────────────────────────────────────────────


class TestProxyKeyOverrideMiddlewareWiring:
    def test_no_key_passes_through_untouched(self) -> None:
        mw = ProxyKeyOverrideMiddleware()
        seen: list[Any] = []

        def handler(request: Any) -> str:
            seen.append(request)
            return "passthrough"

        class _Req:
            runtime = None
            state: dict[str, Any] = {}

        assert mw.wrap_model_call(_Req(), handler) == "passthrough"
        assert seen[0].__class__.__name__ == "_Req"  # original request, no override

    def test_key_present_rekeys_model(self, proxy_env: dict[str, str]) -> None:
        mw = ProxyKeyOverrideMiddleware()
        captured: dict[str, Any] = {}

        class _Req:
            def __init__(self) -> None:
                self.runtime = None
                self.state = {"proxy_api_key": "sk-engagement-xyz"}
                self.model = _original_chat_model()

            def override(self, *, model: Any) -> "_Req":
                new = _Req()
                new.state = self.state
                new.model = model
                return new

        def handler(request: Any) -> str:
            captured["key"] = request.model.openai_api_key.get_secret_value()
            return "ok"

        assert mw.wrap_model_call(_Req(), handler) == "ok"
        assert captured["key"] == "sk-engagement-xyz"


def test_declares_proxy_api_key_state_channel() -> None:
    """The middleware must DECLARE ``proxy_api_key`` as a state channel.

    The middleware reads ``request.state["proxy_api_key"]``, but the LangGraph
    Platform DROPS an undeclared key from run ``input`` — so without this
    channel a SaaS caller threading the key via input could never populate
    ``request.state``. Declaring it on the middleware's ``state_schema`` makes
    ``create_agent`` register the channel on the compiled graph.
    """
    from langchain.agents import AgentState

    from decepticon.middleware.proxy_key_override import ProxyKeyState

    assert ProxyKeyOverrideMiddleware.state_schema is ProxyKeyState
    assert "proxy_api_key" in ProxyKeyState.__annotations__
    # ``AgentState`` is a TypedDict; runtime ``issubclass`` checks raise on
    # newer typing_extensions. Check the structural merge that matters instead.
    for key, annotation in AgentState.__annotations__.items():
        assert ProxyKeyState.__annotations__[key] == annotation
