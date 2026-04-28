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
        # Default mapping has all four API methods → 3 fallbacks per role.
        models = self.factory.get_fallback_models("recon")
        names = [m.model_name for m in models]
        assert names == [
            "openai/gpt-5-nano",
            "gemini/gemini-2.5-flash-lite",
            # MiniMax has no LOW tier → drops out of the chain.
        ]

    def test_get_fallback_models_high_tier_includes_all_methods(self):
        # decepticon is HIGH; every method has a HIGH model → 3 fallbacks.
        models = self.factory.get_fallback_models("decepticon")
        names = [m.model_name for m in models]
        assert names == [
            "openai/gpt-5.5",
            "gemini/gemini-2.5-pro",
            "minimax/MiniMax-M2.5",
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
        for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "MINIMAX_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_PRIORITY", raising=False)
        monkeypatch.delenv("DECEPTICON_AUTH_CLAUDE_CODE", raising=False)
        creds = _resolve_credentials()
        assert creds.methods == [
            AuthMethod.ANTHROPIC_API,
            AuthMethod.OPENAI_API,
            AuthMethod.GOOGLE_API,
            AuthMethod.MINIMAX_API,
        ]
