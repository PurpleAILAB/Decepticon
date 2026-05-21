"""Unit tests for decepticon.llm.debate — adversarial debate validation."""

import pytest

from decepticon.core.schemas import DebateVerdict
from decepticon.llm.debate import (
    AdvocateRebuttal,
    SkepticOpinion,
    adjudicate,
    debate_policy,
    run_debate,
    skipped_record,
)
from decepticon.llm.models import ModelProfile


def _invoke_returning(obj):
    """Build a StructuredInvoke closure that always yields ``obj``."""

    async def _invoke(prompt, schema):
        return obj

    return _invoke


class TestAdjudicate:
    def test_skeptic_concedes_upholds_cross_family(self):
        skeptic = SkepticOpinion(reachable=True, exploitable=True, confidence=0.9)
        verdict, credibility = adjudicate(skeptic, None, cross_family=True)
        assert verdict == DebateVerdict.UPHELD
        assert credibility == 1.0

    def test_upheld_same_family_is_capped(self):
        skeptic = SkepticOpinion(reachable=True, exploitable=True, confidence=0.9)
        verdict, credibility = adjudicate(skeptic, None, cross_family=False)
        assert verdict == DebateVerdict.UPHELD
        assert credibility <= 0.8

    def test_refuted_when_advocate_concedes(self):
        skeptic = SkepticOpinion(
            reachable=False,
            exploitable=False,
            strongest_objection="sink is sanitized",
            confidence=0.8,
        )
        rebuttal = AdvocateRebuttal(objection_holds=True, confidence=0.8)
        verdict, credibility = adjudicate(skeptic, rebuttal, cross_family=True)
        assert verdict == DebateVerdict.REFUTED
        assert credibility < 0.3

    def test_uncertain_when_advocate_rebuts(self):
        skeptic = SkepticOpinion(reachable=False, exploitable=True, confidence=0.6)
        rebuttal = AdvocateRebuttal(objection_holds=False, confidence=0.6)
        verdict, credibility = adjudicate(skeptic, rebuttal, cross_family=True)
        assert verdict == DebateVerdict.UNCERTAIN
        assert 0.3 <= credibility <= 0.8

    def test_confident_refutation_lowers_credibility(self):
        skeptic = SkepticOpinion(reachable=False, exploitable=False, confidence=1.0)
        rebuttal = AdvocateRebuttal(objection_holds=True, confidence=1.0)
        _, low_conf_cred = adjudicate(
            SkepticOpinion(reachable=False, exploitable=False, confidence=0.5),
            AdvocateRebuttal(objection_holds=True, confidence=0.5),
            cross_family=True,
        )
        _, high_conf_cred = adjudicate(skeptic, rebuttal, cross_family=True)
        assert high_conf_cred < low_conf_cred

    def test_credibility_stays_in_bounds(self):
        for reach, expl, oh in [(True, True, None), (False, False, True), (False, True, False)]:
            skeptic = SkepticOpinion(reachable=reach, exploitable=expl, confidence=1.0)
            rebuttal = None if oh is None else AdvocateRebuttal(objection_holds=oh, confidence=1.0)
            _, credibility = adjudicate(skeptic, rebuttal, cross_family=True)
            assert 0.0 <= credibility <= 1.0


@pytest.mark.asyncio
class TestRunDebate:
    async def test_upheld_skips_advocate(self):
        skeptic = SkepticOpinion(reachable=True, exploitable=True, confidence=0.8)
        record = await run_debate(
            finding_summary="SQLi in /search",
            poc_evidence="payload triggered sqlite_master leak",
            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            primary_model_id="anthropic/claude-sonnet-4-6",
            skeptic_model_id="openai/gpt-5-nano",
            cross_family=True,
            skeptic_invoke=_invoke_returning(skeptic),
            advocate_invoke=_invoke_returning(AdvocateRebuttal(objection_holds=False)),
        )
        assert record.verdict == DebateVerdict.UPHELD
        assert len(record.rounds) == 1  # advocate never spoke
        assert record.cross_family is True

    async def test_refuted_runs_advocate(self):
        skeptic = SkepticOpinion(
            reachable=False,
            exploitable=False,
            strongest_objection="negative control also fires",
            confidence=0.85,
        )
        record = await run_debate(
            finding_summary="SSTI in template",
            poc_evidence="{{7*7}} reflected",
            cvss_vector="",
            primary_model_id="anthropic/claude-sonnet-4-6",
            skeptic_model_id="openai/gpt-5-nano",
            cross_family=True,
            skeptic_invoke=_invoke_returning(skeptic),
            advocate_invoke=_invoke_returning(
                AdvocateRebuttal(objection_holds=True, rebuttal="conceded", confidence=0.8)
            ),
        )
        assert record.verdict == DebateVerdict.REFUTED
        assert len(record.rounds) == 2
        assert record.refutation_summary == "negative control also fires"

    async def test_skipped_record_shape(self):
        record = skipped_record("anthropic/claude-sonnet-4-6", "no cross-family model")
        assert record.verdict == DebateVerdict.SKIPPED
        assert record.credibility == 1.0
        assert record.cross_family is False


class TestDebatePolicy:
    def test_env_off_overrides_everything(self):
        assert debate_policy("critical", profile=ModelProfile.MAX, env="off") is False

    def test_env_all_overrides_everything(self):
        assert debate_policy("low", profile=ModelProfile.TEST, env="all") is True

    def test_env_critical_high(self):
        assert debate_policy("high", profile=ModelProfile.ECO, env="critical-high") is True
        assert debate_policy("low", profile=ModelProfile.ECO, env="critical-high") is False

    def test_profile_test_never_debates(self):
        assert debate_policy("critical", profile=ModelProfile.TEST, env="") is False

    def test_profile_max_always_debates(self):
        assert debate_policy("low", profile=ModelProfile.MAX, env="") is True

    def test_profile_eco_debates_critical_high_only(self):
        assert debate_policy("critical", profile=ModelProfile.ECO, env="") is True
        assert debate_policy("high", profile=ModelProfile.ECO, env="") is True
        assert debate_policy("medium", profile=ModelProfile.ECO, env="") is False
