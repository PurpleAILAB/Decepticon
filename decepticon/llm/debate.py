"""Adversarial multi-model debate validation.

MDASH's "debate-driven validation": before a CRITICAL/HIGH finding is
promoted, a skeptic model *from a different provider family* argues it is
a false positive; the advocate (the verifier's own model) rebuts; a
deterministic adjudicator assigns a posterior credibility score. A finding
the skeptic cannot refute gains credibility; one it refutes is blocked.

This module is the pure debate engine — structured-output schemas, prompt
text, the deterministic adjudicator, the orchestrator, and the cost
policy. It performs no LLM calls itself: :func:`run_debate` takes injected
``*_invoke`` closures so tests pass fakes and production passes
LLM-backed closures (see :func:`structured_invoker`).

Cross-family model selection lives in :mod:`decepticon.llm.ensemble`.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from decepticon.core.schemas import DebateRecord, DebateRound, DebateVerdict
from decepticon.llm.ensemble import family_of
from decepticon.llm.models import ModelProfile

# ── Structured-output schemas ────────────────────────────────────────
# Kept separate from the persisted DebateRecord/DebateRound so the LLM
# response schema can evolve without touching the on-disk format.


class SkepticOpinion(BaseModel):
    """A skeptic's verdict on whether a finding is a false positive."""

    reachable: bool = Field(
        description="True if the vulnerable code path is genuinely reachable by an attacker"
    )
    exploitable: bool = Field(
        description="True if the vulnerability is genuinely exploitable, not just theoretical"
    )
    strongest_objection: str = Field(
        default="",
        description="The single strongest argument that this finding is a false positive",
    )
    objections: list[str] = Field(
        default_factory=list, description="All material objections raised"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence in this assessment (0-1)"
    )


class AdvocateRebuttal(BaseModel):
    """The advocate's answer to the skeptic's strongest objection."""

    objection_holds: bool = Field(
        description="True if the skeptic's objection is correct and the finding does NOT hold"
    )
    rebuttal: str = Field(
        default="", description="Concrete answer to the objection, citing PoC evidence"
    )
    residual_doubt: str = Field(
        default="", description="Any doubt that remains even after the rebuttal"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence in this rebuttal (0-1)"
    )


# ── Prompts ──────────────────────────────────────────────────────────

SKEPTIC_PROMPT = """You are a skeptical, independent security reviewer. A red-team \
verifier has produced a candidate finding and a proof-of-concept. Your job is to \
find the STRONGEST argument that this is a FALSE POSITIVE — that the bug is not \
actually reachable, not actually exploitable, or that the PoC's success signal is \
an artifact. You are rewarded for a sound refutation, not for agreeing.

Look hard for: unreachable code paths, input sanitized before the sink, success \
patterns a benign request also triggers (a weak negative control), authentication \
that is not really bypassed, and environmental or harness artifacts.

FINDING:
{finding_summary}

PROOF-OF-CONCEPT EVIDENCE:
{poc_evidence}

CVSS VECTOR: {cvss_vector}

Decide whether the vulnerability is genuinely reachable and genuinely exploitable, \
give your single strongest objection, and rate your confidence."""

ADVOCATE_PROMPT = """You are the verifier who produced this finding. A skeptic has \
challenged it. Answer the skeptic's strongest objection with concrete evidence from \
the proof-of-concept. If the objection is correct and the finding does not hold, \
concede honestly — a false positive that ships poisons every downstream stage.

FINDING:
{finding_summary}

PROOF-OF-CONCEPT EVIDENCE:
{poc_evidence}

SKEPTIC'S STRONGEST OBJECTION:
{objection}

State whether the objection holds, give your rebuttal, and rate your confidence."""


# ── Deterministic adjudication ───────────────────────────────────────

# Credibility below this floor blocks promotion of a CRITICAL/HIGH finding.
CREDIBILITY_FLOOR = 0.3

# An UPHELD verdict from a same-family debate is capped here — the skeptic
# shares the primary's weights, so its agreement is a weaker independence
# signal than a genuine cross-family review.
_SAME_FAMILY_UPHELD_CAP = 0.8


def adjudicate(
    skeptic: SkepticOpinion,
    rebuttal: AdvocateRebuttal | None,
    *,
    cross_family: bool,
) -> tuple[DebateVerdict, float]:
    """Score a debate deterministically — no LLM, fully testable.

    - skeptic concedes (reachable AND exploitable) → ``UPHELD``, base 1.0
    - skeptic refutes, advocate concedes the objection → ``REFUTED``, base 0.15
    - skeptic refutes, advocate rebuts → ``UNCERTAIN``, base 0.55
    - a same-family ``UPHELD`` is capped at 0.8 (weaker independence)

    The base score is nudged by ±0.1 scaled by the lower of the two
    confidences — a confident upholding rises, a confident refutation falls.
    """
    if skeptic.reachable and skeptic.exploitable:
        verdict = DebateVerdict.UPHELD
        credibility = 1.0
    elif rebuttal is None:
        verdict = DebateVerdict.UNCERTAIN
        credibility = 0.5
    elif rebuttal.objection_holds:
        verdict = DebateVerdict.REFUTED
        credibility = 0.15
    else:
        verdict = DebateVerdict.UNCERTAIN
        credibility = 0.55

    conf = skeptic.confidence
    if rebuttal is not None:
        conf = min(conf, rebuttal.confidence)
    nudge = (conf - 0.5) * 0.2
    if verdict == DebateVerdict.UPHELD:
        credibility += nudge
    elif verdict == DebateVerdict.REFUTED:
        credibility -= nudge

    if verdict == DebateVerdict.UPHELD and not cross_family:
        credibility = min(credibility, _SAME_FAMILY_UPHELD_CAP)

    credibility = max(0.0, min(1.0, round(credibility, 3)))
    return verdict, credibility


def _adjudication_text(verdict: DebateVerdict, credibility: float, cross_family: bool) -> str:
    independence = "cross-family" if cross_family else "same-family"
    table = {
        DebateVerdict.UPHELD: "skeptic could not refute the finding",
        DebateVerdict.REFUTED: "skeptic produced a sound refutation the advocate conceded",
        DebateVerdict.UNCERTAIN: "skeptic raised doubt the advocate could not fully resolve",
        DebateVerdict.SKIPPED: "debate not run",
    }
    return f"{verdict.value} ({independence}, credibility={credibility}): {table[verdict]}"


# ── Debate orchestration ─────────────────────────────────────────────

# (prompt, structured-output schema) -> awaitable of the structured object.
StructuredInvoke = Callable[[str, type], Awaitable[Any]]


def structured_invoker(model: Any) -> StructuredInvoke:
    """Wrap a chat model into a :data:`StructuredInvoke` closure."""

    async def _invoke(prompt: str, schema: type) -> Any:
        return await model.with_structured_output(schema).ainvoke(prompt)

    return _invoke


async def run_debate(
    *,
    finding_summary: str,
    poc_evidence: str,
    cvss_vector: str,
    primary_model_id: str,
    skeptic_model_id: str,
    cross_family: bool,
    skeptic_invoke: StructuredInvoke,
    advocate_invoke: StructuredInvoke,
) -> DebateRecord:
    """Run one skeptic→advocate exchange and adjudicate it.

    The skeptic argues the finding is a false positive; only when it
    refutes does the advocate get a turn. ``*_invoke`` are injected so the
    debate is unit-testable without live models.
    """
    skeptic_prompt = SKEPTIC_PROMPT.format(
        finding_summary=finding_summary,
        poc_evidence=poc_evidence,
        cvss_vector=cvss_vector or "(not provided)",
    )
    skeptic: SkepticOpinion = await skeptic_invoke(skeptic_prompt, SkepticOpinion)
    # Explicit two-branch assignment so every path provably initializes
    # `refuted` (keeps CodeQL's uninitialized-variable analysis happy).
    if skeptic.reachable and skeptic.exploitable:
        refuted = False
    else:
        refuted = True

    rounds: list[DebateRound] = [
        DebateRound(
            role="skeptic",
            model=skeptic_model_id,
            family=family_of(skeptic_model_id),
            argument=skeptic.strongest_objection,
            refuted=refuted,
            confidence=skeptic.confidence,
        )
    ]

    rebuttal: AdvocateRebuttal | None = None
    if refuted:
        advocate_prompt = ADVOCATE_PROMPT.format(
            finding_summary=finding_summary,
            poc_evidence=poc_evidence,
            objection=skeptic.strongest_objection or "(the finding is not exploitable)",
        )
        rebuttal = await advocate_invoke(advocate_prompt, AdvocateRebuttal)
        if rebuttal is not None:
            rounds.append(
                DebateRound(
                    role="advocate",
                    model=primary_model_id,
                    family=family_of(primary_model_id),
                    argument=rebuttal.rebuttal,
                    refuted=rebuttal.objection_holds,
                    confidence=rebuttal.confidence,
                )
            )

    verdict, credibility = adjudicate(skeptic, rebuttal, cross_family=cross_family)
    return DebateRecord(
        verdict=verdict,
        credibility=credibility,
        primary_model=primary_model_id,
        skeptic_model=skeptic_model_id,
        primary_family=family_of(primary_model_id),
        skeptic_family=family_of(skeptic_model_id),
        cross_family=cross_family,
        rounds=rounds,
        refutation_summary=skeptic.strongest_objection,
        rebuttal_summary=rebuttal.rebuttal if rebuttal else "",
        adjudication=_adjudication_text(verdict, credibility, cross_family),
        debated_at=datetime.now(timezone.utc).isoformat(),
    )


def skipped_record(primary_model_id: str, reason: str) -> DebateRecord:
    """Build a ``SKIPPED`` debate record (no independent skeptic available)."""
    return DebateRecord(
        verdict=DebateVerdict.SKIPPED,
        credibility=1.0,
        primary_model=primary_model_id,
        primary_family=family_of(primary_model_id),
        cross_family=False,
        adjudication=f"skipped: {reason}",
        debated_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Cost / opt-in policy ─────────────────────────────────────────────


def _is_high_severity(severity: str) -> bool:
    return (severity or "").strip().lower() in ("critical", "high")


def debate_policy(
    severity: str,
    *,
    profile: ModelProfile | str,
    env: str | None,
) -> bool:
    """Decide whether to debate a finding of a given severity.

    The ``DECEPTICON_DEBATE`` env value (``off`` / ``all`` /
    ``critical-high``) overrides the ``ModelProfile`` default
    (max → always, eco → CRITICAL/HIGH only, test → never).
    """
    e = (env or "").strip().lower()
    if e in ("off", "none", "false", "0", "disabled"):
        return False
    if e in ("all", "always", "on", "true", "1"):
        return True
    if e in ("critical-high", "critical_high", "criticalhigh", "high"):
        return _is_high_severity(severity)

    prof = profile if isinstance(profile, ModelProfile) else ModelProfile(profile)
    if prof == ModelProfile.TEST:
        return False
    if prof == ModelProfile.MAX:
        return True
    return _is_high_severity(severity)  # eco


def debate_enabled(severity: str) -> bool:
    """Resolve :func:`debate_policy` from the process environment."""
    profile_raw = os.getenv("DECEPTICON_MODEL_PROFILE", "eco").strip().lower()
    try:
        profile = ModelProfile(profile_raw)
    except ValueError:
        profile = ModelProfile.ECO
    return debate_policy(severity, profile=profile, env=os.getenv("DECEPTICON_DEBATE", ""))


def debate_globally_disabled() -> bool:
    """True when ``DECEPTICON_DEBATE`` is explicitly turned off."""
    return os.getenv("DECEPTICON_DEBATE", "").strip().lower() in (
        "off",
        "none",
        "false",
        "0",
        "disabled",
    )
