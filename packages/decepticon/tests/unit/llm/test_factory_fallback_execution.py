"""Execution-level tests for the primary→fallback chain.

``tests/unit/llm/test_factory.py`` already covers how ``LLMFactory``
RESOLVES the fallback chain (model ids in expected order). These tests
exercise what actually happens at request time when a provider FAILS:

  (a) primary raises a retryable error  → ``ModelFallbackMiddleware``
      reroutes to the configured fallback and a result is returned;
  (b) every provider in the chain raises → the factory's actionable
      ``RuntimeError`` (translated by ``_reraise_with_actionable_message``)
      is the final exception that surfaces;
  (c) happy path: primary succeeds → fallbacks are never invoked.

The seam: ``_ProxiedChatOpenAI.invoke`` calls ``super().invoke`` which
resolves to ``BaseChatModel.invoke``. Monkeypatching that single method
at the class level lets us drive both ``_ProxiedChatOpenAI``'s upstream
error translation **and** ``ModelFallbackMiddleware.wrap_model_call``'s
retry-on-exception logic end-to-end, without touching the network.
"""

from __future__ import annotations

import pytest
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from decepticon.llm.factory import LLMFactory
from decepticon_core.types.llm import (
    Credentials,
    LLMModelMapping,
    ModelProfile,
    ProxyConfig,
)


# A retryable, provider-shaped error. The class name matches the
# substring ``_reraise_with_actionable_message`` looks for ("ratelimit"),
# so ``_ProxiedChatOpenAI.invoke`` will rewrap it into the actionable
# RuntimeError that user-facing CLI / LangGraph serde finally sees.
class RateLimitError(Exception):
    """Stand-in for openai.RateLimitError that doesn't need an httpx.Response."""


def _make_factory() -> LLMFactory:
    proxy = ProxyConfig(url="http://localhost:4000", api_key="test-key")
    creds = Credentials.all_api_methods()
    mapping = LLMModelMapping.from_credentials_and_profile(creds, ModelProfile.ECO)
    return LLMFactory(proxy, mapping)


def _make_request(model: BaseChatModel) -> ModelRequest:
    return ModelRequest(
        model=model,
        messages=[HumanMessage("hello")],
    )


def _handler(request: ModelRequest) -> AIMessage:
    """Minimal handler stand-in for the agent runtime.

    ``ModelFallbackMiddleware`` invokes the handler with the current
    request and re-invokes it with ``request.override(model=fallback)``
    on each retry. The handler returning ``request.model.invoke(...)``
    routes back through ``_ProxiedChatOpenAI.invoke`` so we exercise its
    error translation on the way out.
    """
    return request.model.invoke(request.messages)


@pytest.fixture
def chain():
    """Primary + fallback chain for the recon role.

    Recon resolves to ``anthropic/claude-haiku-4-5`` with 5 fallbacks —
    enough surface to prove the middleware actually walks the list.
    """
    factory = _make_factory()
    primary = factory.get_model("recon")
    fallbacks = factory.get_fallback_models("recon")
    assert fallbacks, "fixture expects a non-empty fallback chain"
    return primary, fallbacks


class TestFallbackExecution:
    """End-to-end execution through ModelFallbackMiddleware.

    Patches ``BaseChatModel.invoke`` (the call ``_ProxiedChatOpenAI``
    delegates to via ``super().invoke``) so each model decides its own
    behaviour based on ``self.model_name``. This keeps the test free of
    network/proxy state while still driving the real factory-built
    objects and the real middleware.
    """

    def test_primary_failure_uses_fallback(self, monkeypatch, chain) -> None:
        primary, fallbacks = chain
        fallback_used = fallbacks[0]
        ok_message = AIMessage(content="from-fallback")
        calls: list[str] = []

        def fake_invoke(self, *args, **kwargs):
            calls.append(self.model_name)
            if self.model_name == primary.model_name:
                raise RateLimitError("code: 429 quota exceeded")
            if self.model_name == fallback_used.model_name:
                return ok_message
            # Any further fallbacks would also raise so a missed
            # short-circuit shows up as a different error class.
            raise AssertionError(f"unexpected fallback hit: {self.model_name}")

        monkeypatch.setattr(BaseChatModel, "invoke", fake_invoke)

        mw = ModelFallbackMiddleware(*fallbacks)
        result = mw.wrap_model_call(_make_request(primary), _handler)

        assert result is ok_message
        # Primary attempted first, then exactly the first fallback.
        assert calls == [primary.model_name, fallback_used.model_name]

    def test_all_providers_fail_surfaces_actionable_error(self, monkeypatch, chain) -> None:
        primary, fallbacks = chain
        calls: list[str] = []

        def fake_invoke(self, *args, **kwargs):
            calls.append(self.model_name)
            raise RateLimitError("code: 429 all out of quota")

        monkeypatch.setattr(BaseChatModel, "invoke", fake_invoke)

        mw = ModelFallbackMiddleware(*fallbacks)

        with pytest.raises(RuntimeError) as excinfo:
            mw.wrap_model_call(_make_request(primary), _handler)

        # Every model in the chain was attempted (primary + each fallback).
        assert calls == [primary.model_name, *[m.model_name for m in fallbacks]]

        # The middleware re-raises the LAST exception. ``_ProxiedChatOpenAI``
        # already translated it into the actionable rate-limit RuntimeError,
        # so the user-visible error names the failing model + remediation.
        msg = str(excinfo.value)
        assert fallbacks[-1].model_name in msg
        assert "rate limit" in msg.lower()
        assert "DECEPTICON_AUTH_PRIORITY" in msg
        # And the original transport-shaped error is preserved as the cause
        # — otherwise we'd be papering over the real failure.
        assert isinstance(excinfo.value.__cause__, RateLimitError)

    def test_happy_path_does_not_touch_fallbacks(self, monkeypatch, chain) -> None:
        primary, fallbacks = chain
        ok_message = AIMessage(content="from-primary")
        calls: list[str] = []

        def fake_invoke(self, *args, **kwargs):
            calls.append(self.model_name)
            if self.model_name == primary.model_name:
                return ok_message
            raise AssertionError(
                f"fallback {self.model_name} must not be called when primary succeeds"
            )

        monkeypatch.setattr(BaseChatModel, "invoke", fake_invoke)

        mw = ModelFallbackMiddleware(*fallbacks)
        result = mw.wrap_model_call(_make_request(primary), _handler)

        assert result is ok_message
        assert calls == [primary.model_name]
