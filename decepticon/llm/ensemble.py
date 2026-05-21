"""Multi-model ensemble routing — deliberate cross-family model selection.

Decepticon's tier system (HIGH/MID/LOW) is a *cost* knob: under a single
set of credentials it stays inside one provider family, and cross-family
models only appear in the chain as *failover* targets. MDASH's core insight
is that "no single model is best at every stage" — an independent model from
a *different* family is the most useful second opinion.

This module adds, on top of the existing ``resolve_chain`` primitive:

  - ``family_of`` — classify a LiteLLM model id into a provider family.
  - ``select_cross_family`` — pick a model from a family different from a
    given primary, with graceful degradation when only one family exists.
  - ``resolve_ensemble`` — per-role ``EnsembleAssignment`` carrying the
    primary reasoner, a same-tier counterpoint, and a cheap LOW-tier
    debater, all family-aware.

Everything here is pure: no network, no LiteLLM calls. Phase 2 (adversarial
debate validation) consumes ``family_of`` and ``select_cross_family``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from decepticon.llm.models import (
    Credentials,
    LLMModelMapping,
    ModelProfile,
    Tier,
    resolve_chain,
)

# ── Provider family classification ──────────────────────────────────────
# Maps a family name to substring markers. A model id is classified by
# matching its trailing slug first (so ``openrouter/anthropic/claude-...``
# and ``bedrock/anthropic.claude-...`` both resolve to ``anthropic``), then
# the whole id. ``unknown`` is returned when nothing matches and is never
# treated as a valid cross-family counterpart.

MODEL_FAMILIES: dict[str, tuple[str, ...]] = {
    "anthropic": ("claude",),
    "openai": ("gpt-", "o1-", "o3-", "o4-", "codex", "openai"),
    "google": ("gemini", "gemma"),
    "xai": ("grok",),
    "meta": ("llama", "nemotron"),
    "mistral": ("mistral", "codestral", "magistral", "ministral"),
    "deepseek": ("deepseek",),
    "minimax": ("minimax", "abab"),
    "qwen": ("qwen", "qwq"),
    "cohere": ("command-", "c4ai"),
    "moonshot": ("kimi", "moonshot"),
    "zai": ("glm",),
    "perplexity": ("sonar", "pplx"),
}

UNKNOWN_FAMILY = "unknown"

# Debater turns are exploratory but must produce structured output — a
# little above the precision-execution default, well below creative.
DEBATER_TEMPERATURE = 0.3


def family_of(model_id: str) -> str:
    """Classify a LiteLLM model id into a provider family.

    Matches the trailing slug first so provider/gateway prefixes
    (``openrouter/``, ``auth/``, ``copilot/``, ``bedrock/``) do not
    mislead the classification. Returns :data:`UNKNOWN_FAMILY` when no
    marker matches — callers must treat ``unknown`` as *not* a valid
    cross-family counterpart.
    """
    if not model_id:
        return UNKNOWN_FAMILY
    mid = model_id.lower().strip()
    slug = mid.rsplit("/", 1)[-1]
    for haystack in (slug, mid):
        for family, markers in MODEL_FAMILIES.items():
            if any(marker in haystack for marker in markers):
                return family
    return UNKNOWN_FAMILY


@dataclass(frozen=True)
class CrossFamilySelection:
    """Outcome of a cross-family model search.

    ``cross_family`` is the load-bearing field: ``True`` means ``model_id``
    is a genuinely independent counterpart. ``False`` with a non-None
    ``model_id`` means only a same-family alternative was available (still
    useful as a counterpoint, but not an independent debater). ``model_id``
    is ``None`` only when no alternative model resolves at all.
    """

    model_id: str | None
    family: str
    cross_family: bool
    reason: str


def select_cross_family(
    *,
    primary_model_id: str,
    credentials: Credentials,
    tier: Tier,
) -> CrossFamilySelection:
    """Pick a model from a family different from ``primary_model_id``.

    Walks ``resolve_chain(tier, credentials)`` — the same ordered,
    cross-family chain the failover system uses — and returns:

      1. the first model whose family differs from the primary's
         (``cross_family=True``); else
      2. the first same-family model that is not the primary itself
         (``cross_family=False`` — a weaker second opinion); else
      3. ``model_id=None`` when nothing resolves (empty credentials, or a
         single model identical to the primary).
    """
    primary_family = family_of(primary_model_id)
    chain = resolve_chain(tier, credentials)

    for model in chain:
        fam = family_of(model)
        if fam != UNKNOWN_FAMILY and fam != primary_family:
            return CrossFamilySelection(
                model_id=model,
                family=fam,
                cross_family=True,
                reason="cross-family counterpart from the credentials chain",
            )

    for model in chain:
        if model != primary_model_id:
            return CrossFamilySelection(
                model_id=model,
                family=family_of(model),
                cross_family=False,
                reason="no cross-family credential configured; same-family alternative",
            )

    return CrossFamilySelection(
        model_id=None,
        family=UNKNOWN_FAMILY,
        cross_family=False,
        reason="no alternative model resolvable from credentials",
    )


@dataclass(frozen=True)
class EnsembleAssignment:
    """Per-role ensemble: primary reasoner + family-aware secondaries.

    ``counterpoint`` is a different-family model at the role's own tier
    (a peer second opinion). ``debater`` is a different-family LOW-tier
    model (a cheap adversarial reviewer, MDASH-style). Either may be
    ``None`` when the user has only one provider family configured —
    callers must degrade gracefully.
    """

    role: str
    primary: str
    primary_family: str
    counterpoint: str | None
    counterpoint_family: str
    debater: str | None
    debater_family: str
    fallbacks: list[str] = field(default_factory=list)
    cross_family_available: bool = False


def resolve_ensemble(
    role: str,
    *,
    mapping: LLMModelMapping | None = None,
    credentials: Credentials | None = None,
    profile: ModelProfile | str | None = None,
    default_role: str | None = None,
) -> EnsembleAssignment:
    """Resolve the full ensemble assignment for an agent role.

    When ``mapping`` is omitted it is built from ``credentials`` (or the
    all-API-methods default) and ``profile`` (or ``eco``). The primary and
    its fallbacks come straight from the existing role assignment; the
    counterpoint is the first different-family model already in that
    chain; the debater is resolved fresh at LOW tier via
    :func:`select_cross_family`.
    """
    if mapping is None:
        credentials = credentials or Credentials.all_api_methods()
        resolved_profile = ModelProfile(profile) if profile is not None else ModelProfile.ECO
        mapping = LLMModelMapping.from_credentials_and_profile(credentials, resolved_profile)

    assignment = mapping.get_assignment(role, default_role=default_role)
    primary = assignment.primary
    primary_family = family_of(primary)

    # The role's own chain ([primary, *fallbacks]) is resolve_chain at the
    # role's tier — pick the counterpoint straight from it, no re-resolve.
    counterpoint: str | None = None
    counterpoint_family = UNKNOWN_FAMILY
    for model in assignment.fallbacks:
        fam = family_of(model)
        if fam != UNKNOWN_FAMILY and fam != primary_family:
            counterpoint = model
            counterpoint_family = fam
            break

    # The debater is a cheap LOW-tier cross-family model — needs the raw
    # credentials to resolve a LOW chain. Without credentials, fall back
    # to the counterpoint (best effort).
    debater: str | None = None
    debater_family = UNKNOWN_FAMILY
    if credentials is not None:
        low = select_cross_family(
            primary_model_id=primary,
            credentials=credentials,
            tier=Tier.LOW,
        )
        if low.cross_family:
            debater = low.model_id
            debater_family = low.family
    if debater is None and counterpoint is not None:
        debater = counterpoint
        debater_family = counterpoint_family

    return EnsembleAssignment(
        role=role,
        primary=primary,
        primary_family=primary_family,
        counterpoint=counterpoint,
        counterpoint_family=counterpoint_family,
        debater=debater,
        debater_family=debater_family,
        fallbacks=list(assignment.fallbacks),
        cross_family_available=debater is not None,
    )
