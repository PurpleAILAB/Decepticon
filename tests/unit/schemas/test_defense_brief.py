"""Unit tests for decepticon.schemas.defense_brief Pydantic models."""

from __future__ import annotations

from datetime import datetime

from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    DefenseBrief,
    DefenseRecommendation,
    ReAttackOutcome,
    VerificationResult,
)

# ── DefenseActionType ─────────────────────────────────────────────────────────


def test_defense_action_type_values() -> None:
    assert DefenseActionType.BLOCK_PORT == "block_port"
    assert DefenseActionType.ADD_FIREWALL_RULE == "add_firewall_rule"
    assert DefenseActionType.DISABLE_SERVICE == "disable_service"
    assert DefenseActionType.RESTART_SERVICE == "restart_service"
    assert DefenseActionType.UPDATE_CONFIG == "update_config"
    assert DefenseActionType.KILL_PROCESS == "kill_process"
    assert DefenseActionType.REVOKE_CREDENTIAL == "revoke_credential"
    assert len(DefenseActionType) == 7


# ── ReAttackOutcome ───────────────────────────────────────────────────────────


def test_re_attack_outcome_values() -> None:
    assert ReAttackOutcome.BLOCKED == "blocked"
    assert ReAttackOutcome.PASSED == "passed"
    assert ReAttackOutcome.PARTIAL == "partial"
    assert ReAttackOutcome.ERROR == "error"
    assert len(ReAttackOutcome) == 4


# ── DefenseRecommendation ─────────────────────────────────────────────────────


def test_defense_recommendation_valid() -> None:
    rec = DefenseRecommendation(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/8080",
        parameters={"chain": "INPUT", "rule": "DROP"},
        priority=2,
        rationale="Exposed admin port",
    )
    assert rec.action_type == DefenseActionType.BLOCK_PORT
    assert rec.target == "tcp/8080"
    assert rec.parameters == {"chain": "INPUT", "rule": "DROP"}
    assert rec.priority == 2
    assert rec.rationale == "Exposed admin port"


def test_defense_recommendation_defaults() -> None:
    rec = DefenseRecommendation(
        action_type=DefenseActionType.DISABLE_SERVICE,
        target="sshd",
        rationale="Unnecessary remote access service",
    )
    assert rec.priority == 1
    assert rec.parameters == {}


# ── DefenseBrief ──────────────────────────────────────────────────────────────


def test_defense_brief_valid() -> None:
    rec = DefenseRecommendation(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/22",
        rationale="SSH exposed",
    )
    brief = DefenseBrief(
        finding_ref="FIND-001",
        finding_title="Exposed SSH Service",
        severity="high",
        attack_vector="SSH brute-force over tcp/22",
        affected_assets=["10.0.0.1", "10.0.0.2"],
        recommended_actions=[rec],
        evidence_summary="Nmap scan revealed open port 22",
    )
    assert brief.finding_ref == "FIND-001"
    assert brief.finding_title == "Exposed SSH Service"
    assert brief.severity == "high"
    assert brief.attack_vector == "SSH brute-force over tcp/22"
    assert brief.affected_assets == ["10.0.0.1", "10.0.0.2"]
    assert len(brief.recommended_actions) == 1
    assert brief.evidence_summary == "Nmap scan revealed open port 22"
    assert isinstance(brief.created_at, datetime)


def test_defense_brief_minimal() -> None:
    brief = DefenseBrief(
        finding_ref="FIND-002",
        finding_title="Weak Config",
        severity="medium",
        attack_vector="Misconfigured service allows unauthenticated access",
    )
    assert brief.finding_ref == "FIND-002"
    assert brief.affected_assets == []
    assert brief.recommended_actions == []
    assert brief.evidence_summary == ""
    assert isinstance(brief.created_at, datetime)


# ── DefenseActionResult ───────────────────────────────────────────────────────


def test_defense_action_result_with_rollback() -> None:
    result = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/8080",
        success=True,
        message="Port blocked successfully",
        rollback_command="iptables -D INPUT -p tcp --dport 8080 -j DROP",
    )
    assert result.success is True
    assert result.rollback_command == "iptables -D INPUT -p tcp --dport 8080 -j DROP"
    assert isinstance(result.executed_at, datetime)


def test_defense_action_result_no_rollback() -> None:
    result = DefenseActionResult(
        action_type=DefenseActionType.KILL_PROCESS,
        target="malware_payload",
        success=True,
        message="Process killed",
    )
    assert result.rollback_command is None


# ── VerificationResult ────────────────────────────────────────────────────────


def test_verification_result_blocked() -> None:
    action_result = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/22",
        success=True,
        message="Port blocked",
    )
    vr = VerificationResult(
        finding_ref="FIND-001",
        defense_actions_applied=[action_result],
        re_attack_outcome=ReAttackOutcome.BLOCKED,
        re_attack_details="SSH connection refused after iptables rule applied",
    )
    assert vr.finding_ref == "FIND-001"
    assert vr.re_attack_outcome == ReAttackOutcome.BLOCKED
    assert len(vr.defense_actions_applied) == 1
    assert isinstance(vr.verified_at, datetime)


def test_verification_result_passed() -> None:
    vr = VerificationResult(
        finding_ref="FIND-002",
        re_attack_outcome=ReAttackOutcome.PASSED,
    )
    assert vr.re_attack_outcome == ReAttackOutcome.PASSED
    assert vr.defense_actions_applied == []
    assert vr.re_attack_details == ""


# ── JSON roundtrip ────────────────────────────────────────────────────────────


def test_defense_brief_json_roundtrip() -> None:
    rec = DefenseRecommendation(
        action_type=DefenseActionType.REVOKE_CREDENTIAL,
        target="user:alice",
        rationale="Compromised account",
        priority=1,
        parameters={"type": "user_account"},
    )
    original = DefenseBrief(
        finding_ref="FIND-003",
        finding_title="Compromised Credential",
        severity="critical",
        attack_vector="Credential stuffing via exposed API",
        affected_assets=["api.example.com"],
        recommended_actions=[rec],
        evidence_summary="Valid login with leaked password",
    )
    json_str = original.model_dump_json()
    restored = DefenseBrief.model_validate_json(json_str)

    assert restored.finding_ref == original.finding_ref
    assert restored.finding_title == original.finding_title
    assert restored.severity == original.severity
    assert restored.attack_vector == original.attack_vector
    assert restored.affected_assets == original.affected_assets
    assert len(restored.recommended_actions) == 1
    assert restored.recommended_actions[0].action_type == DefenseActionType.REVOKE_CREDENTIAL
    assert restored.recommended_actions[0].parameters == {"type": "user_account"}
    assert restored.evidence_summary == original.evidence_summary
