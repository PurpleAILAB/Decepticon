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
            "deepseek/deepseek-chat",
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
            "deepseek/deepseek-reasoner",
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
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_CLAUDE_CODE", raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.ANTHROPIC_API]

    def test_oauth_only(self, monkeypatch):
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "MINIMAX_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("DECEPTICON_AUTH_CLAUDE_CODE", "true")
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [AuthMethod.ANTHROPIC_OAUTH]

    def test_oauth_plus_api_priority_default(self, monkeypatch):
        # Default priority is anthropic_oauth > anthropic_api > openai_api ...
        monkeypatch.setenv("DECEPTICON_AUTH_CLAUDE_CODE", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-12345")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai-12345")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
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
