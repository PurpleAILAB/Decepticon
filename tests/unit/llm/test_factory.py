"""Unit tests for decepticon.llm.factory."""

import asyncio

import pytest

from decepticon.llm.factory import LLMFactory, _resolve_credentials
from decepticon.llm.models import (
    AuthMethod,
    Credentials,
    LLMModelMapping,
    ModelProfile,
    ProxyConfig,
)


class TestLLMFactory:
    def setup_method(self):
        self.proxy = ProxyConfig(url="http://localhost:4000", api_key="test-key")
        # Build an explicit mapping so the test doesn't depend on env vars.
        creds = Credentials.all_api_methods()
        self.mapping = LLMModelMapping.from_credentials_and_profile(creds, ModelProfile.ECO)
        self.factory = LLMFactory(self.proxy, self.mapping)

    def test_factory_initializes(self):
        assert self.factory.proxy_url == "http://localhost:4000"

    def test_get_model_returns_chat_model(self):
        model = self.factory.get_model("recon")
        assert model is not None
        assert model.model_name == "anthropic/claude-haiku-4-5"

    def test_get_model_caches_instances(self):
        m1 = self.factory.get_model("recon")
        m2 = self.factory.get_model("recon")
        assert m1 is m2

    def test_get_model_different_roles_different_models(self):
        recon = self.factory.get_model("recon")
        decepticon = self.factory.get_model("decepticon")
        assert recon is not decepticon
        assert recon.model_name != decepticon.model_name

    def test_get_model_unknown_role_raises(self):
        with pytest.raises(KeyError, match="No model assignment"):
            self.factory.get_model("nonexistent")

    def test_router_accessible(self):
        assert self.factory.router is not None

    def test_get_fallback_models_full_chain(self):
        models = self.factory.get_fallback_models("recon")
        names = [m.model_name for m in models]
        assert names == [
            "openai/gpt-5-nano",
            "gemini/gemini-2.5-flash-lite",
            "deepseek/deepseek-v4-flash",
            "openrouter/anthropic/claude-haiku-4-5",
            "nvidia_nim/meta/llama-3.2-3b-instruct",
        ]

    def test_get_fallback_models_high_tier_includes_all_methods(self):
        models = self.factory.get_fallback_models("decepticon")
        names = [m.model_name for m in models]
        assert names == [
            "openai/gpt-5.5",
            "gemini/gemini-2.5-pro",
            "minimax/MiniMax-M2.5",
            "deepseek/deepseek-v4-pro",
            "xai/grok-3",
            "mistral/mistral-large-latest",
            "openrouter/anthropic/claude-opus-4-7",
            "nvidia_nim/meta/llama-3.3-70b-instruct",
        ]

    def test_get_fallback_models_without_fallback(self):
        # Single-credential mapping → no fallback.
        creds = Credentials(methods=[AuthMethod.OPENAI_API])
        mapping = LLMModelMapping.from_credentials_and_profile(creds, ModelProfile.ECO)
        factory = LLMFactory(self.proxy, mapping)
        assert factory.get_fallback_models("recon") == []

    def test_explicit_credentials_param(self):
        # Constructor accepts a Credentials object instead of a full mapping.
        creds = Credentials(methods=[AuthMethod.OPENAI_API])
        factory = LLMFactory(self.proxy, credentials=creds, profile=ModelProfile.ECO)
        assert factory.get_model("decepticon").model_name == "openai/gpt-5.5"


class TestLLMFactoryHealthCheck:
    def test_health_check_returns_false_when_no_proxy(self):
        proxy = ProxyConfig(url="http://localhost:19999")
        factory = LLMFactory(proxy, mapping=LLMModelMapping())
        assert asyncio.run(factory.health_check()) is False


class TestResolveCredentials:
    def test_real_keys_only(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-12345")
        monkeypatch.setenv("OPENAI_API_KEY", "your-openai-key-here")  # placeholder
        for k in (
            "GEMINI_API_KEY",
            "MINIMAX_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "OLLAMA_API_BASE",
            "OLLAMA_MODEL",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_CLAUDE_CODE", raising=False)
        for flag in (
            "DECEPTICON_AUTH_CHATGPT",
            "DECEPTICON_AUTH_COPILOT",
            "DECEPTICON_AUTH_GEMINI",
            "DECEPTICON_AUTH_GROK",
            "DECEPTICON_AUTH_PERPLEXITY",
        ):
            monkeypatch.delenv(flag, raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.ANTHROPIC_API]

    def test_oauth_only(self, monkeypatch):
        for k in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "MINIMAX_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "OLLAMA_API_BASE",
            "OLLAMA_MODEL",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("DECEPTICON_AUTH_CLAUDE_CODE", "true")
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        for flag in (
            "DECEPTICON_AUTH_CHATGPT",
            "DECEPTICON_AUTH_COPILOT",
            "DECEPTICON_AUTH_GEMINI",
            "DECEPTICON_AUTH_GROK",
            "DECEPTICON_AUTH_PERPLEXITY",
        ):
            monkeypatch.delenv(flag, raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.ANTHROPIC_OAUTH]

    def test_oauth_plus_api_priority_default(self, monkeypatch):
        # Default priority is anthropic_oauth > anthropic_api > openai_api ...
        monkeypatch.setenv("DECEPTICON_AUTH_CLAUDE_CODE", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-12345")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai-12345")
        for k in (
            "GEMINI_API_KEY",
            "MINIMAX_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "OLLAMA_API_BASE",
            "OLLAMA_MODEL",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        for flag in (
            "DECEPTICON_AUTH_CHATGPT",
            "DECEPTICON_AUTH_COPILOT",
            "DECEPTICON_AUTH_GEMINI",
            "DECEPTICON_AUTH_GROK",
            "DECEPTICON_AUTH_PERPLEXITY",
        ):
            monkeypatch.delenv(flag, raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [
            AuthMethod.ANTHROPIC_OAUTH,
            AuthMethod.ANTHROPIC_API,
            AuthMethod.OPENAI_API,
        ]

    def test_explicit_priority_override(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_AUTH_PRIORITY", "openai_api,anthropic_api")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-12345")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai-12345")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_CLAUDE_CODE", raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.OPENAI_API, AuthMethod.ANTHROPIC_API]

    def test_placeholder_falls_back_to_all_api_methods(self, monkeypatch):
        """When every detected method is a placeholder/missing, the resolver
        falls back to the all-API-methods inventory so module-level agent
        constructors stay importable in CI / dev shells without keys."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "your-anthropic-key-here")
        for k in (
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "MINIMAX_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "OLLAMA_API_BASE",
            "OLLAMA_MODEL",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_CLAUDE_CODE", raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [
            AuthMethod.ANTHROPIC_API,
            AuthMethod.OPENAI_API,
            AuthMethod.GOOGLE_API,
            AuthMethod.MINIMAX_API,
            AuthMethod.DEEPSEEK_API,
            AuthMethod.XAI_API,
            AuthMethod.MISTRAL_API,
            AuthMethod.OPENROUTER_API,
            AuthMethod.NVIDIA_API,
        ]

    def test_ollama_local_only_returns_ollama_chain(self, monkeypatch):
        """Issue #106: a user with only OLLAMA_API_BASE / OLLAMA_MODEL set
        (no API keys, no OAuth) must get a chain of one — Ollama only.
        Falling back to all-API-methods would produce 401 errors on every
        provider the user doesn't have."""
        for k in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "MINIMAX_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "DECEPTICON_AUTH_PRIORITY",
            "DECEPTICON_AUTH_CLAUDE_CODE",
            "DECEPTICON_AUTH_CHATGPT",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("OLLAMA_API_BASE", "http://host.docker.internal:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3-coder:30b")
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.OLLAMA_LOCAL]

    def test_explicit_priority_with_ollama_local(self, monkeypatch):
        """User opts into Ollama via explicit priority — the resolver
        recognizes it as configured when OLLAMA_API_BASE is set."""
        monkeypatch.setenv("DECEPTICON_AUTH_PRIORITY", "ollama_local,anthropic_api")
        monkeypatch.setenv("OLLAMA_API_BASE", "http://host.docker.internal:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3-coder:30b")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-12345")
        for k in (
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "MINIMAX_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "DECEPTICON_AUTH_CLAUDE_CODE",
            "DECEPTICON_AUTH_CHATGPT",
        ):
            monkeypatch.delenv(k, raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.OLLAMA_LOCAL, AuthMethod.ANTHROPIC_API]


# ── Temperature handling (issue #107) ───────────────────────────────────


class TestTemperatureDrop:
    """Claude Opus 4.7 rejects ``temperature`` regardless of route. The
    factory must drop it on every Opus 4 surface (anthropic/, auth/,
    openrouter/anthropic/) and keep it for everyone else."""

    def setup_method(self):
        from decepticon.llm.factory import _model_drops_temperature

        self._drops = _model_drops_temperature

    def test_anthropic_opus_drops_temperature(self):
        assert self._drops("anthropic/claude-opus-4-7") is True

    def test_oauth_opus_drops_temperature(self):
        assert self._drops("auth/claude-opus-4-7") is True

    def test_openrouter_opus_drops_temperature(self):
        assert self._drops("openrouter/anthropic/claude-opus-4-7") is True

    def test_sonnet_keeps_temperature(self):
        assert self._drops("anthropic/claude-sonnet-4-6") is False

    def test_haiku_keeps_temperature(self):
        assert self._drops("anthropic/claude-haiku-4-5") is False

    def test_openai_keeps_temperature(self):
        assert self._drops("openai/gpt-5.5") is False

    def test_ollama_keeps_temperature(self):
        assert self._drops("ollama_chat/qwen3-coder:30b") is False


# ── Actionable error translation (issue #107 + community feedback) ──────


class TestActionableErrorTranslation:
    """The OSS user complaint: every upstream failure surfaces as 'An
    internal error occurred', stripping the message that would tell them
    what to fix. Each branch below verifies one class of error gets
    rewritten with a remediation hint and the model id that hit the
    failure."""

    def setup_method(self):
        from decepticon.llm.factory import _reraise_with_actionable_message

        self._translate = _reraise_with_actionable_message

    def test_no_fallback_model_group_branch(self):
        exc = Exception(
            "litellm.BadRequestError: ... No fallback model group found "
            "for original model_group=anthropic/claude-opus-4-7."
        )
        with pytest.raises(RuntimeError) as info:
            self._translate(exc, "anthropic/claude-opus-4-7")
        msg = str(info.value)
        assert "no provider fallback" in msg
        assert "anthropic/claude-opus-4-7" in msg
        assert "DECEPTICON_AUTH_PRIORITY" in msg

    def test_400_bad_request_branch(self):
        # openai.BadRequestError carries 'Error code: 400' in repr.
        exc = Exception("Error code: 400 - {'error': {'message': 'temperature is deprecated'}}")
        type(exc).__name__  # noqa: B018 — sanity, ensures Exception default name
        with pytest.raises(RuntimeError) as info:
            self._translate(exc, "anthropic/claude-opus-4-7")
        assert "rejected the request (400)" in str(info.value)

    def test_401_authentication_branch(self):
        exc = type("AuthenticationError", (Exception,), {})("Error code: 401 - invalid_api_key")
        with pytest.raises(RuntimeError) as info:
            self._translate(exc, "openai/gpt-5.5")
        msg = str(info.value)
        assert "credentials (401)" in msg
        assert "decepticon onboard --reset" in msg

    def test_429_ratelimit_branch(self):
        exc = type("RateLimitError", (Exception,), {})("Error code: 429")
        with pytest.raises(RuntimeError) as info:
            self._translate(exc, "anthropic/claude-opus-4-7")
        msg = str(info.value)
        assert "rate limit (429)" in msg
        assert "DECEPTICON_AUTH_PRIORITY" in msg

    def test_404_notfound_with_ollama_hint(self):
        exc = type("NotFoundError", (Exception,), {})("Error code: 404 - model not found")
        with pytest.raises(RuntimeError) as info:
            self._translate(exc, "ollama_chat/nonexistent")
        msg = str(info.value)
        assert "404" in msg
        assert "OLLAMA_MODEL" in msg

    def test_unmatched_error_passes_through(self):
        # Anything we don't recognize must NOT raise — the caller's
        # ``raise`` follows and re-raises the original exception with
        # full traceback.
        exc = ValueError("something completely unrelated")
        # Should not raise from the helper.
        self._translate(exc, "anthropic/claude-opus-4-7")


# ── DeepSeek V4 Pro reasoning_content passthrough ────────────────────────


class TestDeepSeekReasoningContent:
    """Verify reasoning_content survives both the non-streaming and streaming
    paths so it can be sent back on subsequent API turns."""

    def test_create_chat_result_extracts_reasoning_content(self):
        """Non-streaming: _create_chat_result captures reasoning_content
        from the response dict's choice message."""
        from unittest.mock import patch

        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        # Simulate the OpenAI response dict with reasoning_content
        response_dict = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Four",
                        "reasoning_content": "I think therefore I am",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

        # Mock the parent's _create_chat_result to return a ChatResult without reasoning_content
        msg = AIMessage(content="Four", additional_kwargs={})
        parent_result = ChatResult(generations=[ChatGeneration(message=msg)])

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_create_chat_result",
            return_value=parent_result,
        ):
            instance = object.__new__(_DeepSeekThinkingChatOpenAI)
            result = instance._create_chat_result(response_dict)

        assert (
            result.generations[0].message.additional_kwargs["reasoning_content"]
            == "I think therefore I am"
        )

    def test_create_chat_result_skips_when_absent(self):
        """Non-streaming: no crash when reasoning_content is missing."""
        from unittest.mock import patch

        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        response_dict = {
            "choices": [
                {"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
            ],
            "usage": {},
        }

        msg = AIMessage(content="hi", additional_kwargs={})
        parent_result = ChatResult(generations=[ChatGeneration(message=msg)])

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_create_chat_result",
            return_value=parent_result,
        ):
            instance = object.__new__(_DeepSeekThinkingChatOpenAI)
            result = instance._create_chat_result(response_dict)

        assert "reasoning_content" not in result.generations[0].message.additional_kwargs

    def test_convert_chunk_injects_reasoning_content(self):
        """Streaming: _convert_chunk_to_generation_chunk captures
        reasoning_content from the raw delta and injects it into
        AIMessageChunk.additional_kwargs."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        # Build a fake raw SSE chunk dict with reasoning_content in the delta
        raw_chunk = {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "Let me think...",
                    },
                    "finish_reason": None,
                }
            ],
        }

        # The parent's _convert_chunk_to_generation_chunk builds the
        # ChatGenerationChunk but ignores reasoning_content. We mock it
        # to return a chunk without reasoning_content, then verify our
        # override injects it.
        base_msg = AIMessageChunk(content="", additional_kwargs={})
        base_chunk = ChatGenerationChunk(message=base_msg)

        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        # Bind the real method to our mock instance
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=base_chunk,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        assert result is not None
        assert result.message.additional_kwargs["reasoning_content"] == "Let me think..."

    def test_convert_chunk_no_reasoning_leaves_kwargs_clean(self):
        """Streaming: when delta has no reasoning_content, additional_kwargs
        is not polluted."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        raw_chunk = {
            "choices": [
                {
                    "delta": {"role": "assistant", "content": "hi"},
                    "finish_reason": None,
                }
            ],
        }

        base_msg = AIMessageChunk(content="hi", additional_kwargs={})
        base_chunk = ChatGenerationChunk(message=base_msg)

        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=base_chunk,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        assert result is not None
        assert "reasoning_content" not in result.message.additional_kwargs

    def test_reasoning_content_accumulates_across_chunks(self):
        """Streaming: reasoning_content from multiple chunks concatenates
        via AIMessageChunk.__add__ (merge_dicts)."""
        from langchain_core.messages import AIMessageChunk

        c1 = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Let me "})
        c2 = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "think..."})
        c3 = AIMessageChunk(content="Hello!", additional_kwargs={})

        merged = c1 + c2 + c3
        assert merged.additional_kwargs["reasoning_content"] == "Let me think..."
        assert merged.content == "Hello!"

    def test_get_request_payload_injects_reasoning_content(self):
        """Outbound: _get_request_payload injects reasoning_content from
        AIMessage.additional_kwargs into serialized assistant message dicts."""
        from unittest.mock import patch

        from langchain_core.messages import AIMessage, HumanMessage

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="hello",
                additional_kwargs={"reasoning_content": "thinking..."},
            ),
        ]

        # Mock super()._get_request_payload to return a payload without reasoning_content
        mock_payload = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            "model": "deepseek/deepseek-v4-pro",
        }

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_get_request_payload",
            return_value=mock_payload,
        ):
            instance = object.__new__(_DeepSeekThinkingChatOpenAI)
            payload = instance._get_request_payload(messages)

        assert payload["messages"][1]["reasoning_content"] == "thinking..."
        assert "reasoning_content" not in payload["messages"][0]
        assert payload["extra_body"]["thinking"] == {"type": "enabled"}
        assert payload["reasoning_effort"] == "high"

    def test_convert_chunk_empty_reasoning_content_ignored(self):
        """Streaming: empty string reasoning_content in delta is ignored."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        raw_chunk = {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "hi",
                        "reasoning_content": "",
                    },
                    "finish_reason": None,
                }
            ],
        }

        base_msg = AIMessageChunk(content="hi", additional_kwargs={})
        base_chunk = ChatGenerationChunk(message=base_msg)
        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=base_chunk,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        # Empty string is falsy — should not pollute additional_kwargs
        assert "reasoning_content" not in result.message.additional_kwargs

    def test_convert_chunk_none_delta_no_crash(self):
        """Streaming: None delta in choices does not crash."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        raw_chunk = {
            "choices": [
                {
                    "delta": None,
                    "finish_reason": "stop",
                }
            ],
        }

        base_msg = AIMessageChunk(content="", additional_kwargs={})
        base_chunk = ChatGenerationChunk(message=base_msg)
        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=base_chunk,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        assert result is not None
        assert "reasoning_content" not in result.message.additional_kwargs

    def test_convert_chunk_empty_choices_no_crash(self):
        """Streaming: empty choices array does not crash."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        raw_chunk = {"choices": []}

        base_msg = AIMessageChunk(content="", additional_kwargs={})
        base_chunk = ChatGenerationChunk(message=base_msg)
        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=base_chunk,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        assert result is not None
        assert "reasoning_content" not in result.message.additional_kwargs

    def test_convert_chunk_parent_returns_none(self):
        """Streaming: when parent returns None, we return None too."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        raw_chunk = {"type": "content.delta"}  # parent returns None for these
        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=None,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        assert result is None

    def test_convert_chunk_beta_stream_format(self):
        """Streaming: handles beta.chat.completions.stream nested chunk format."""
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        # Some LangChain versions nest under "chunk" key
        raw_chunk = {
            "chunk": {
                "choices": [
                    {
                        "delta": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "Thinking via beta format...",
                        },
                        "finish_reason": None,
                    }
                ],
            },
        }

        base_msg = AIMessageChunk(content="", additional_kwargs={})
        base_chunk = ChatGenerationChunk(message=base_msg)
        instance = MagicMock(spec=_DeepSeekThinkingChatOpenAI)
        method = _DeepSeekThinkingChatOpenAI._convert_chunk_to_generation_chunk

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_convert_chunk_to_generation_chunk",
            return_value=base_chunk,
        ):
            result = method(instance, raw_chunk, AIMessageChunk, None)

        assert (
            result.message.additional_kwargs["reasoning_content"] == "Thinking via beta format..."
        )

    def test_get_request_payload_multiple_assistant_messages(self):
        """Outbound: each assistant message gets its own reasoning_content."""
        from unittest.mock import patch

        from langchain_core.messages import AIMessage, HumanMessage

        from decepticon.llm.factory import _DeepSeekThinkingChatOpenAI

        messages = [
            HumanMessage(content="q1"),
            AIMessage(content="a1", additional_kwargs={"reasoning_content": "thought1"}),
            HumanMessage(content="q2"),
            AIMessage(content="a2", additional_kwargs={"reasoning_content": "thought2"}),
        ]

        mock_payload = {
            "messages": [
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
                {"role": "assistant", "content": "a2"},
            ],
            "model": "deepseek/deepseek-v4-pro",
        }

        with patch.object(
            _DeepSeekThinkingChatOpenAI.__bases__[0],
            "_get_request_payload",
            return_value=mock_payload,
        ):
            instance = object.__new__(_DeepSeekThinkingChatOpenAI)
            payload = instance._get_request_payload(messages)

        assert payload["messages"][1]["reasoning_content"] == "thought1"
        assert payload["messages"][3]["reasoning_content"] == "thought2"
        assert "reasoning_content" not in payload["messages"][0]
        assert "reasoning_content" not in payload["messages"][2]

    def test_model_detection(self):
        """Factory routes deepseek-v4-pro through the thinking subclass."""
        from decepticon.llm.factory import _model_is_deepseek_thinking

        assert _model_is_deepseek_thinking("deepseek/deepseek-v4-pro") is True
        assert _model_is_deepseek_thinking("deepseek/deepseek-reasoner") is True
        assert _model_is_deepseek_thinking("deepseek/deepseek-v4-flash") is False
        assert _model_is_deepseek_thinking("deepseek/deepseek-chat") is False
        assert _model_is_deepseek_thinking("openai/gpt-5.5") is False
