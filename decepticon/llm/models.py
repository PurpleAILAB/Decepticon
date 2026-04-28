"""LLM model definitions — tier-based, credentials-aware mappings.

Three orthogonal axes control model selection:

  Tier        — model power level (HIGH / MID / LOW)
  AuthMethod  — specific way to authenticate (anthropic_api,
                anthropic_oauth, openai_api, google_api, minimax_api)
  Profile     — eco (per-agent tier) / max (all HIGH) / test (all LOW)

The profile decides each agent's *tier*. The user's *credentials inventory*
— a list of AuthMethods in priority order — decides the fallback chain at
that tier. Each AuthMethod is a distinct credential: Anthropic API key
and Claude Code OAuth are two different methods, can both be configured,
and can be ordered independently in the priority list.

Examples
--------
User has [anthropic_api, openai_api]. Profile=eco.
  decepticon (HIGH) → primary=anthropic/claude-opus-4-7, fallback=openai/gpt-5.5
  recon (LOW)       → primary=anthropic/claude-haiku-4-5, fallback=openai/gpt-5-nano

User has [anthropic_oauth, anthropic_api]. Profile=eco.
  decepticon (HIGH) → primary=auth/claude-opus-4-7, fallback=anthropic/claude-opus-4-7
  (OAuth subscription primary, paid API as fallback when subscription quota hits.)

User has [anthropic_oauth] only. Profile=eco.
  decepticon (HIGH) → primary=auth/claude-opus-4-7, fallback=None

User has [openai_api]. Profile=eco.
  decepticon (HIGH) → primary=openai/gpt-5.5, fallback=None
  recon (LOW)       → primary=openai/gpt-5-nano, fallback=None

Tier × AuthMethod matrix
------------------------
                    HIGH                          MID                            LOW
  anthropic_api    claude-opus-4-7               claude-sonnet-4-6              claude-haiku-4-5
  anthropic_oauth  auth/claude-opus-4-7          auth/claude-sonnet-4-6         auth/claude-haiku-4-5
  openai_api       gpt-5.5                       gpt-5.4                        gpt-5-nano
  google_api       gemini-2.5-pro                gemini-2.5-flash               gemini-2.5-flash-lite
  minimax_api      MiniMax-M2.5                  MiniMax-M2.5-lightning         — (falls through)

Profiles
--------
  eco   per-agent tier (production default)
  max   every agent on HIGH (high-value targets)
  test  every agent on LOW (development / CI)

Model identifiers verified against provider docs as of 2026-04-28.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# ── Tier and AuthMethod enums ───────────────────────────────────────────


class Tier(StrEnum):
    """Model power level — orthogonal to authentication method."""

    HIGH = "high"
    MID = "mid"
    LOW = "low"


class AuthMethod(StrEnum):
    """A specific way to authenticate to a model provider.

    Each method routes to its own model identifier in LiteLLM and
    requires its own credential. Anthropic has two methods (API key
    via x-api-key, and Claude Code OAuth via Bearer token); these are
    independent credentials and can both be configured and prioritized
    separately.
    """

    ANTHROPIC_API = "anthropic_api"
    ANTHROPIC_OAUTH = "anthropic_oauth"  # Claude Code subscription
    OPENAI_API = "openai_api"
    # OPENAI_OAUTH = "openai_oauth"  # Codex subscription — coming soon
    GOOGLE_API = "google_api"
    MINIMAX_API = "minimax_api"


# ── Tier × AuthMethod → model_id matrix ─────────────────────────────────
# When a (method, tier) entry is missing (e.g. minimax_api LOW), the chain
# resolver skips that method for that tier and falls through to the next
# method in priority order.

METHOD_MODELS: dict[AuthMethod, dict[Tier, str]] = {
    AuthMethod.ANTHROPIC_API: {
        Tier.HIGH: "anthropic/claude-opus-4-7",
        Tier.MID: "anthropic/claude-sonnet-4-6",
        Tier.LOW: "anthropic/claude-haiku-4-5",
    },
    AuthMethod.ANTHROPIC_OAUTH: {
        Tier.HIGH: "auth/claude-opus-4-7",
        Tier.MID: "auth/claude-sonnet-4-6",
        Tier.LOW: "auth/claude-haiku-4-5",
    },
    AuthMethod.OPENAI_API: {
        Tier.HIGH: "openai/gpt-5.5",
        Tier.MID: "openai/gpt-5.4",
        Tier.LOW: "openai/gpt-5-nano",
    },
    AuthMethod.GOOGLE_API: {
        Tier.HIGH: "gemini/gemini-2.5-pro",
        Tier.MID: "gemini/gemini-2.5-flash",
        Tier.LOW: "gemini/gemini-2.5-flash-lite",
    },
    AuthMethod.MINIMAX_API: {
        Tier.HIGH: "minimax/MiniMax-M2.5",
        Tier.MID: "minimax/MiniMax-M2.5-lightning",
        # MiniMax line has no LOW-tier light variant — falls through to
        # the next configured method.
    },
}


# ── Per-agent tier and temperature ──────────────────────────────────────
# eco profile uses these directly. max promotes everything to HIGH.
# test demotes everything to LOW.

AGENT_TIERS: dict[str, Tier] = {
    # HIGH — deep reasoning, multi-step planning, source-level analysis,
    # long context accumulation. Failure cost is mission-critical.
    "decepticon": Tier.HIGH,
    "exploiter": Tier.HIGH,
    "patcher": Tier.HIGH,
    "contract_auditor": Tier.HIGH,
    "analyst": Tier.HIGH,
    "vulnresearch": Tier.HIGH,
    # MID — precision execution, code generation, structured judgment.
    # Tool-heavy with moderate iteration.
    "exploit": Tier.MID,
    "detector": Tier.MID,
    "verifier": Tier.MID,
    "postexploit": Tier.MID,
    "defender": Tier.MID,
    "ad_operator": Tier.MID,
    "cloud_hunter": Tier.MID,
    "reverser": Tier.MID,
    # LOW — high-throughput, low reasoning depth. Recon / triage / docs.
    "soundwave": Tier.LOW,
    "recon": Tier.LOW,
    "scanner": Tier.LOW,
}

AGENT_TEMPERATURES: dict[str, float] = {
    "decepticon": 0.4,
    "soundwave": 0.4,
    "exploit": 0.3,
    "exploiter": 0.2,
    "detector": 0.2,
    "verifier": 0.2,
    "patcher": 0.2,
    "postexploit": 0.3,
    "defender": 0.2,
    "ad_operator": 0.2,
    "cloud_hunter": 0.2,
    "contract_auditor": 0.2,
    "reverser": 0.2,
    "analyst": 0.2,
    "scanner": 0.2,
    "vulnresearch": 0.4,
    "recon": 0.3,
}


# ── Profile ─────────────────────────────────────────────────────────────


class ModelProfile(StrEnum):
    """Tier preset that overlays AGENT_TIERS."""

    ECO = "eco"
    MAX = "max"
    TEST = "test"


def _resolve_tier(role: str, profile: ModelProfile) -> Tier:
    """Resolve the effective tier for a role under a profile."""
    if profile == ModelProfile.MAX:
        return Tier.HIGH
    if profile == ModelProfile.TEST:
        return Tier.LOW
    return AGENT_TIERS[role]


# ── Credentials ─────────────────────────────────────────────────────────


class Credentials(BaseModel):
    """User's available LLM credentials, in priority order.

    ``methods`` lists each configured AuthMethod, ordered by user
    preference. Each entry is an independent credential — having both
    ``ANTHROPIC_OAUTH`` and ``ANTHROPIC_API`` is valid and useful
    (subscription primary, paid API as fallback). Order in this list
    becomes the model fallback order at every tier.
    """

    methods: list[AuthMethod] = Field(default_factory=list)

    @classmethod
    def all_api_methods(cls) -> Credentials:
        """All four API methods in default priority order. Used as a
        development convenience and for tests that want a fully-populated
        inventory without specifying it inline."""
        return cls(
            methods=[
                AuthMethod.ANTHROPIC_API,
                AuthMethod.OPENAI_API,
                AuthMethod.GOOGLE_API,
                AuthMethod.MINIMAX_API,
            ]
        )


def resolve_chain(tier: Tier, credentials: Credentials) -> list[str]:
    """Build the model chain (primary first, then fallbacks) for a tier.

    Walks ``credentials.methods`` in order, picking the model for each
    method at the given tier from ``METHOD_MODELS``. When a method has
    no entry at that tier (minimax_api LOW), it's skipped and the chain
    continues with the next method.
    """
    chain: list[str] = []
    for method in credentials.methods:
        model = METHOD_MODELS[method].get(tier)
        if model is not None:
            chain.append(model)
    return chain


# ── Configuration models ────────────────────────────────────────────────


class ProxyConfig(BaseModel):
    """LiteLLM proxy connection settings."""

    url: str = "http://localhost:4000"
    api_key: str = "sk-decepticon-master"
    timeout: int = 120
    max_retries: int = 2


class ModelAssignment(BaseModel):
    """Primary + ordered fallbacks for an agent role.

    ``fallbacks`` mirrors the credentials priority list past the
    primary: every method the user configured below the first one
    appears here, in order. langchain's ``ModelFallbackMiddleware``
    walks these in sequence on primary failure.
    """

    primary: str
    fallbacks: list[str] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int | None = None

    @property
    def fallback(self) -> str | None:
        """First fallback or None. Kept for callers that read the
        single-fallback shape; new code should use ``fallbacks``."""
        return self.fallbacks[0] if self.fallbacks else None

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v


class LLMModelMapping(BaseModel):
    """Role → ModelAssignment, built from credentials + profile.

    Construct via :meth:`from_credentials_and_profile` or
    :meth:`from_profile` (which assumes all-API-methods credentials).
    """

    assignments: dict[str, ModelAssignment] = Field(default_factory=dict)

    def get_assignment(self, role: str) -> ModelAssignment:
        """Get model assignment for a role.

        Raises KeyError if the role has no assignment (e.g. credentials
        are empty, or the role isn't in AGENT_TIERS).
        """
        if role not in self.assignments:
            raise KeyError(f"No model assignment for role: {role}")
        return self.assignments[role]

    @classmethod
    def from_credentials_and_profile(
        cls,
        credentials: Credentials,
        profile: ModelProfile | str = ModelProfile.ECO,
    ) -> LLMModelMapping:
        """Build a mapping from a credentials inventory + profile.

        For each agent in ``AGENT_TIERS``: resolve the effective tier
        under the profile, then build the chain from credentials. If
        credentials produce no chain at all (empty methods list), the
        role is skipped — callers will fail at LLM init time.
        """
        profile = ModelProfile(profile)
        assignments: dict[str, ModelAssignment] = {}
        for role in AGENT_TIERS:
            tier = _resolve_tier(role, profile)
            chain = resolve_chain(tier, credentials)
            if not chain:
                continue
            assignments[role] = ModelAssignment(
                primary=chain[0],
                fallbacks=chain[1:],
                temperature=AGENT_TEMPERATURES.get(role, 0.7),
            )
        return cls(assignments=assignments)

    @classmethod
    def from_profile(cls, profile: ModelProfile | str) -> LLMModelMapping:
        """Build with the default credentials (all four API methods, default
        priority). Used by tests and dev convenience — production code
        should pass an explicit Credentials inventory."""
        return cls.from_credentials_and_profile(Credentials.all_api_methods(), profile)


# `from __future__ import annotations` defers field-annotation evaluation,
# so pydantic needs a final rebuild pass once every referenced symbol is
# in scope. Skipping this leaves Credentials/LLMModelMapping in a "not
# fully defined" state and any instantiation raises.
Credentials.model_rebuild()
LLMModelMapping.model_rebuild()
ModelAssignment.model_rebuild()
ProxyConfig.model_rebuild()
