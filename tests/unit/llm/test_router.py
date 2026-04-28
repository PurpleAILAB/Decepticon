"""Unit tests for decepticon.llm.router — thin wrapper over LLMModelMapping."""

import pytest

from decepticon.llm.models import (
    AuthMethod,
    Credentials,
    LLMModelMapping,
    ModelAssignment,
    ModelProfile,
)
from decepticon.llm.router import ModelRouter


class TestModelRouter:
    def setup_method(self):
        # Default: all four API methods available, eco profile.
        self.mapping = LLMModelMapping.from_profile(ModelProfile.ECO)
        self.router = ModelRouter(self.mapping)

    def test_resolve_returns_primary(self):
        # recon is LOW; first method is anthropic_api → haiku.
        assert self.router.resolve("recon") == "anthropic/claude-haiku-4-5"

    def test_resolve_decepticon_is_high_tier(self):
        assert self.router.resolve("decepticon") == "anthropic/claude-opus-4-7"

    def test_resolve_with_fallback_returns_chain(self):
        chain = self.router.resolve_with_fallback("recon")
        assert chain[0] == "anthropic/claude-haiku-4-5"
        assert chain[1] == "openai/gpt-5.4-nano"

    def test_resolve_with_fallback_high_tier(self):
        chain = self.router.resolve_with_fallback("decepticon")
        assert chain[0] == "anthropic/claude-opus-4-7"
        assert chain[1] == "openai/gpt-5.5"

    def test_resolve_unknown_role_raises(self):
        with pytest.raises(KeyError, match="No model assignment"):
            self.router.resolve("nonexistent_role")

    def test_get_assignment_returns_full_config(self):
        a = self.router.get_assignment("recon")
        assert isinstance(a, ModelAssignment)
        assert a.primary == "anthropic/claude-haiku-4-5"
        assert a.temperature == 0.3

    def test_resolve_with_single_credential_no_fallback(self):
        creds = Credentials(methods=[AuthMethod.OPENAI_API])
        router = ModelRouter(LLMModelMapping.from_credentials_and_profile(creds))
        chain = router.resolve_with_fallback("decepticon")
        assert chain == ["openai/gpt-5.5"]
