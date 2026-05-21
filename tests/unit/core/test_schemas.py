"""Smoke tests for the eight engagement-planning schemas.

The five new schemas (ThreatProfile, CleanupPlan, AbortPlan, ContactPlan,
DataHandlingPlan) shipped alongside the existing three (RoE, CONOPS,
DeconflictionPlan). These tests pin their default shapes, round-trip
JSON, and the EngagementBundle.save() expansion so soundwave's bundle
generation stays wire-compatible across refactors.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.core.schemas import (
    CONOPS,
    OPPLAN,
    AbortPlan,
    AbortTrigger,
    CleanupArtifact,
    CleanupPlan,
    Contact,
    ContactPlan,
    DataClass,
    DataHandlingPlan,
    DeconflictionPlan,
    EngagementBundle,
    EngagementType,
    FindingConfidence,
    RoE,
    ThreatProfile,
    ThreatTier,
    TriggerSeverity,
)

# ── ThreatProfile ─────────────────────────────────────────────────────


def test_threat_profile_minimum_construction() -> None:
    """Required fields only — the rest carry defaults."""
    tp = ThreatProfile(
        engagement_name="acme-q2",
        actor_name="APT29-like",
        tier=ThreatTier.TIER_3,
        sophistication="nation-state",
        motivation="espionage",
    )

    assert tp.actor_aliases == []
    assert tp.group_id == ""
    assert tp.confidence == FindingConfidence.PROBABLE
    assert tp.version == "1.0"
    assert tp.last_updated  # default factory ran


def test_threat_profile_round_trips_through_json() -> None:
    tp = ThreatProfile(
        engagement_name="acme-q2",
        actor_name="APT29-like",
        actor_aliases=["Cozy Bear"],
        group_id="G0050",
        tier=ThreatTier.TIER_3,
        sophistication="nation-state",
        motivation="espionage",
        initial_access=["T1566.001"],
        key_ttps=["T1059.001", "T1071.001"],
        recent_cti_delta="2026 CTI: OAuth abuse",
    )

    encoded = json.dumps(tp.model_dump())
    rehydrated = ThreatProfile.model_validate_json(encoded)

    assert rehydrated.tier == ThreatTier.TIER_3
    assert rehydrated.group_id == "G0050"
    assert rehydrated.key_ttps == ["T1059.001", "T1071.001"]


# ── CleanupPlan ───────────────────────────────────────────────────────


def test_cleanup_plan_defaults_to_empty_inventory() -> None:
    cp = CleanupPlan(engagement_name="acme-q2")
    assert cp.artifacts == []
    assert "removed=True" in cp.completion_criteria


def test_cleanup_artifact_required_fields() -> None:
    art = CleanupArtifact(
        artifact_type="beacon",
        host="10.1.2.3",
        path="/tmp/.sliver-implant",
        removal_command="rm -f /tmp/.sliver-implant",
    )
    assert art.removed is False
    assert art.verifier_command == ""


# ── AbortPlan ─────────────────────────────────────────────────────────


def test_abort_plan_seeds_three_default_triggers() -> None:
    """The schema default seeds the three baseline triggers. Removing
    the EMERGENCY default would let the agent run through a real
    blue-team incident alert — pin the count so a future refactor that
    drops them fails this test."""
    ap = AbortPlan(engagement_name="acme-q2")
    assert len(ap.halt_triggers) == 3
    assert any(t.severity == TriggerSeverity.EMERGENCY for t in ap.halt_triggers)


def test_abort_plan_ai_safety_gates_defaults() -> None:
    ap = AbortPlan(engagement_name="acme-q2")
    assert ap.hallucination_threshold >= 1
    assert ap.destructive_action_gate is True
    assert ap.output_validation == "verify-evidence-hash"


def test_abort_trigger_can_be_custom() -> None:
    trig = AbortTrigger(
        condition="Network outage on target",
        severity=TriggerSeverity.WARNING,
        response_action="Pause scanning for 5min, resume on healthcheck",
        auto_halt=False,
    )
    assert trig.severity == TriggerSeverity.WARNING


def test_abort_plan_hallucination_threshold_rejects_zero() -> None:
    """``ge=1`` validator on hallucination_threshold prevents a zero
    that would silently disable the gate."""
    with pytest.raises(ValueError):
        AbortPlan(engagement_name="acme-q2", hallucination_threshold=0)


# ── ContactPlan ───────────────────────────────────────────────────────


def test_contact_plan_minimum_construction() -> None:
    operator = Contact(name="Op", role="Primary Operator", channel="signal:+10000000000")
    cp = ContactPlan(engagement_name="acme-q2", primary_operator=operator)
    assert cp.escalation_chain == []
    assert cp.abort_signal_recipient is None
    assert cp.blackout_windows == []


def test_contact_plan_with_escalation_chain() -> None:
    op = Contact(name="Op", role="Primary", channel="email:op@x")
    owner = Contact(name="Eng Lead", role="Engagement Owner", channel="pagerduty:svc-key")
    cp = ContactPlan(
        engagement_name="acme-q2",
        primary_operator=op,
        escalation_chain=[owner],
        abort_signal_recipient=op,
    )
    assert len(cp.escalation_chain) == 1
    assert cp.abort_signal_recipient is op


# ── DataHandlingPlan ──────────────────────────────────────────────────


def test_data_handling_plan_seeds_four_default_classes() -> None:
    """Defaults cover credentials / pii / source-code / business-data
    so engagements without explicit overrides still get conservative
    retention."""
    dh = DataHandlingPlan(engagement_name="acme-q2")
    names = {dc.name for dc in dh.data_classes}
    assert {"credentials", "pii", "source-code", "business-data"} <= names
    assert dh.purge_after_days == 90
    assert dh.chain_of_custody is True


def test_data_handling_plan_compliance_frameworks() -> None:
    dh = DataHandlingPlan(engagement_name="acme-q2", compliance_frameworks=["GDPR", "HIPAA"])
    assert "GDPR" in dh.compliance_frameworks


def test_data_class_retention_rejects_negative() -> None:
    with pytest.raises(ValueError):
        DataClass(name="x", classification="internal", retention_days=-1)


# ── EngagementBundle.save() expansion ─────────────────────────────────


def _minimal_baseline() -> tuple[RoE, CONOPS, OPPLAN, DeconflictionPlan]:
    """The original four required docs — minimal valid values so the
    save() bundle tests aren't gated on RoE/CONOPS schema validation."""
    roe = RoE(
        engagement_name="acme-q2",
        client="Acme",
        start_date="2026-05-21",
        end_date="2026-05-28",
        engagement_type=EngagementType.EXTERNAL,
        testing_window="Mon-Fri 09:00-18:00 KST",
    )
    conops = CONOPS(engagement_name="acme-q2", executive_summary="Quarterly external test.")
    opplan = OPPLAN(engagement_name="acme-q2", threat_profile="APT29-like (Cozy Bear)")
    deconfliction = DeconflictionPlan(engagement_name="acme-q2")
    return roe, conops, opplan, deconfliction


def test_bundle_save_writes_only_baseline_when_expansion_absent(tmp_path: Path) -> None:
    """Backward-compat: callers that don't populate the five expansion
    docs still get the original four files written."""
    roe, conops, opplan, deconfliction = _minimal_baseline()
    bundle = EngagementBundle(roe=roe, conops=conops, opplan=opplan, deconfliction=deconfliction)

    files = bundle.save(str(tmp_path))

    plan_dir = tmp_path / "plan"
    assert sorted(files) == ["conops", "deconfliction", "opplan", "roe"]
    assert {p.name for p in plan_dir.iterdir()} == {
        "roe.json",
        "conops.json",
        "opplan.json",
        "deconfliction.json",
    }


def test_bundle_save_writes_expansion_docs_when_populated(tmp_path: Path) -> None:
    """When the operator supplies the five expansion docs alongside the
    baseline four, save() writes nine files total (the four baseline
    plus all five expansion files with hyphenated names)."""
    roe, conops, opplan, deconfliction = _minimal_baseline()
    operator = Contact(name="Op", role="Primary", channel="email:op@x")

    bundle = EngagementBundle(
        roe=roe,
        conops=conops,
        opplan=opplan,
        deconfliction=deconfliction,
        threat_profile=ThreatProfile(
            engagement_name="acme-q2",
            actor_name="APT29-like",
            tier=ThreatTier.TIER_3,
            sophistication="nation-state",
            motivation="espionage",
        ),
        cleanup=CleanupPlan(engagement_name="acme-q2"),
        abort=AbortPlan(engagement_name="acme-q2"),
        contact=ContactPlan(engagement_name="acme-q2", primary_operator=operator),
        data_handling=DataHandlingPlan(engagement_name="acme-q2"),
    )

    files = bundle.save(str(tmp_path))
    plan_dir = tmp_path / "plan"

    expected = {
        "roe.json",
        "conops.json",
        "opplan.json",
        "deconfliction.json",
        "threat-profile.json",
        "cleanup.json",
        "abort.json",
        "contact.json",
        "data-handling.json",
    }
    assert {p.name for p in plan_dir.iterdir()} == expected
    assert "threat-profile" in files
    assert "data-handling" in files


def test_bundle_save_skips_only_absent_expansion_docs(tmp_path: Path) -> None:
    """Per-doc independence — populating only some expansion fields
    writes only those files, not all-or-nothing."""
    roe, conops, opplan, deconfliction = _minimal_baseline()
    bundle = EngagementBundle(
        roe=roe,
        conops=conops,
        opplan=opplan,
        deconfliction=deconfliction,
        cleanup=CleanupPlan(engagement_name="acme-q2"),
        # threat_profile / abort / contact / data_handling left None
    )

    files = bundle.save(str(tmp_path))
    plan_dir = tmp_path / "plan"

    assert "cleanup" in files
    assert "threat-profile" not in files
    assert not (plan_dir / "threat-profile.json").exists()
    assert (plan_dir / "cleanup.json").exists()
