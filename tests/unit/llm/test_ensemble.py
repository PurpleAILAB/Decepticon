"""Unit tests for decepticon.llm.ensemble — multi-model ensemble routing."""

from decepticon.llm.ensemble import (
    EnsembleAssignment,
    family_of,
    resolve_ensemble,
    select_cross_family,
)
from decepticon.llm.models import (
    AuthMethod,
    Credentials,
    LLMModelMapping,
    ModelProfile,
    Tier,
)


class TestFamilyOf:
    def test_anthropic(self):
        assert family_of("anthropic/claude-opus-4-7") == "anthropic"

    def test_openai(self):
        assert family_of("openai/gpt-5.5") == "openai"
        assert family_of("openai/gpt-5-nano") == "openai"

    def test_google(self):
        assert family_of("gemini/gemini-2.5-pro") == "google"

    def test_xai(self):
        assert family_of("xai/grok-4.3") == "xai"

    def test_meta(self):
        assert family_of("nvidia_nim/meta/llama-3.3-70b-instruct") == "meta"

    def test_minimax(self):
        assert family_of("minimax/MiniMax-M2.5") == "minimax"

    def test_deepseek(self):
        assert family_of("deepseek/deepseek-v4-pro") == "deepseek"

    def test_mistral(self):
        assert family_of("mistral/mistral-large-latest") == "mistral"

    def test_openrouter_mirrored_resolves_to_real_family(self):
        # The trailing slug, not the gateway prefix, decides the family.
        assert family_of("openrouter/anthropic/claude-opus-4-7") == "anthropic"

    def test_bedrock_prefixed(self):
        assert family_of("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0") == "anthropic"

    def test_oauth_prefixed(self):
        assert family_of("auth/claude-opus-4-7") == "anthropic"
        assert family_of("copilot/gpt-5.3-codex") == "openai"

    def test_unknown_returns_unknown(self):
        assert family_of("some-obscure-model-xyz") == "unknown"

    def test_empty_returns_unknown(self):
        assert family_of("") == "unknown"


class TestSelectCrossFamily:
    def test_two_families_picks_cross_family(self):
        creds = Credentials(methods=[AuthMethod.ANTHROPIC_API, AuthMethod.OPENAI_API])
        sel = select_cross_family(
            primary_model_id="anthropic/claude-opus-4-7",
            credentials=creds,
            tier=Tier.LOW,
        )
        assert sel.model_id == "openai/gpt-5-nano"
        assert sel.family == "openai"
        assert sel.cross_family is True

    def test_single_family_returns_same_family_non_none(self):
        creds = Credentials(methods=[AuthMethod.ANTHROPIC_API])
        sel = select_cross_family(
            primary_model_id="anthropic/claude-opus-4-7",
            credentials=creds,
            tier=Tier.LOW,
        )
        # A same-family alternative is still returned — but flagged as not
        # an independent counterpart so debate callers can skip.
        assert sel.model_id == "anthropic/claude-haiku-4-5"
        assert sel.cross_family is False

    def test_empty_credentials_return_none(self):
        sel = select_cross_family(
            primary_model_id="anthropic/claude-opus-4-7",
            credentials=Credentials(methods=[]),
            tier=Tier.LOW,
        )
        assert sel.model_id is None
        assert sel.cross_family is False

    def test_tier_is_respected(self):
        creds = Credentials(methods=[AuthMethod.ANTHROPIC_API, AuthMethod.OPENAI_API])
        high = select_cross_family(
            primary_model_id="anthropic/claude-opus-4-7",
            credentials=creds,
            tier=Tier.HIGH,
        )
        assert high.model_id == "openai/gpt-5.5"


class TestResolveEnsemble:
    def test_eco_profile_decepticon_has_cross_family_secondaries(self):
        creds = Credentials.all_api_methods()
        ens = resolve_ensemble("decepticon", credentials=creds, profile=ModelProfile.ECO)
        assert isinstance(ens, EnsembleAssignment)
        assert ens.primary == "anthropic/claude-opus-4-7"
        assert ens.primary_family == "anthropic"
        # Counterpoint is the first different-family model in the HIGH chain.
        assert ens.counterpoint == "openai/gpt-5.5"
        assert ens.counterpoint_family == "openai"
        # Debater is a cheap LOW-tier cross-family model.
        assert ens.debater == "openai/gpt-5-nano"
        assert ens.cross_family_available is True

    def test_single_family_has_no_secondaries(self):
        creds = Credentials(methods=[AuthMethod.ANTHROPIC_API])
        ens = resolve_ensemble("decepticon", credentials=creds, profile=ModelProfile.ECO)
        assert ens.primary == "anthropic/claude-opus-4-7"
        assert ens.counterpoint is None
        assert ens.debater is None
        assert ens.cross_family_available is False

    def test_test_profile_demotes_primary_to_low(self):
        creds = Credentials.all_api_methods()
        ens = resolve_ensemble("decepticon", credentials=creds, profile=ModelProfile.TEST)
        assert ens.primary == "anthropic/claude-haiku-4-5"

    def test_max_profile_promotes_primary_to_high(self):
        creds = Credentials.all_api_methods()
        ens = resolve_ensemble("scanner", credentials=creds, profile=ModelProfile.MAX)
        assert ens.primary == "anthropic/claude-opus-4-7"

    def test_resolve_from_explicit_mapping(self):
        creds = Credentials.all_api_methods()
        mapping = LLMModelMapping.from_credentials_and_profile(creds, ModelProfile.ECO)
        ens = resolve_ensemble("verifier", mapping=mapping, credentials=creds)
        assert ens.primary == "anthropic/claude-sonnet-4-6"
        assert ens.counterpoint_family == "openai"
