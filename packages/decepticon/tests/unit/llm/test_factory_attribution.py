"""Provider/model attribution logging on the proxied ChatOpenAI wrapper.

When fallback fires through the LiteLLM proxy, operators need to know
which provider actually served each call. The proxied wrapper logs the
served model id extracted from the response metadata after every
successful invoke/ainvoke. Attribution is best-effort: a result lacking
metadata must not raise.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from decepticon.llm.factory import _ProxiedChatOpenAI


def _make_proxy() -> _ProxiedChatOpenAI:
    return _ProxiedChatOpenAI(
        model="anthropic/claude-haiku-4-5",
        base_url="http://localhost:4000",
        api_key=SecretStr("sk-test"),
        timeout=5,
        max_retries=0,
    )


@pytest.fixture
def propagate_decepticon_logs(monkeypatch: pytest.MonkeyPatch):
    # ``decepticon_core.utils.logging`` defaults the parent ``decepticon``
    # logger to ``propagate=False`` so library output doesn't double up
    # in apps that own the root handler. caplog hooks the root logger,
    # so without re-enabling propagation our attribution record never
    # reaches the capture buffer.
    decepticon_log = logging.getLogger("decepticon")
    monkeypatch.setattr(decepticon_log, "propagate", True)


class TestProviderAttributionLogging:
    def test_invoke_logs_served_model_from_response_metadata(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        propagate_decepticon_logs,
    ) -> None:
        served = "anthropic/claude-haiku-4-5-20251022"
        fake = AIMessage(content="ok", response_metadata={"model_name": served})

        def fake_invoke(self, *args, **kwargs):
            return fake

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)

        model = _make_proxy()
        with caplog.at_level(logging.DEBUG, logger="decepticon"):
            result = model.invoke("hi")

        assert result is fake
        messages = [r.getMessage() for r in caplog.records]
        assert any(served in m and "anthropic/claude-haiku-4-5" in m for m in messages), (
            f"No attribution log mentioning served={served}. Got: {messages}"
        )

    def test_ainvoke_logs_served_model_from_response_metadata(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        propagate_decepticon_logs,
    ) -> None:
        served = "openai/gpt-5-nano-2025-10-01"
        fake = AIMessage(content="ok", response_metadata={"model_name": served})

        async def fake_ainvoke(self, *args, **kwargs):
            return fake

        monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

        model = _make_proxy()
        with caplog.at_level(logging.DEBUG, logger="decepticon"):
            result = asyncio.run(model.ainvoke("hi"))

        assert result is fake
        messages = [r.getMessage() for r in caplog.records]
        assert any(served in m for m in messages), (
            f"No attribution log mentioning served={served}. Got: {messages}"
        )

    def test_invoke_missing_metadata_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch, propagate_decepticon_logs
    ) -> None:
        # Result with no response_metadata must still flow through cleanly.
        fake = AIMessage(content="ok")

        def fake_invoke(self, *args, **kwargs):
            return fake

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)

        model = _make_proxy()
        # Must not raise even though metadata is absent.
        assert model.invoke("hi") is fake

    def test_invoke_broken_metadata_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch, propagate_decepticon_logs
    ) -> None:
        # Pathological return value (non-AIMessage) — attribution is
        # best-effort and must never propagate exceptions to callers.
        sentinel = object()

        def fake_invoke(self, *args, **kwargs):
            return sentinel

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)

        model = _make_proxy()
        assert model.invoke("hi") is sentinel
