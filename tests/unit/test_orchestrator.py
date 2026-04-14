"""Unit tests for decepticon.orchestrator.VaccineOrchestrator."""

from __future__ import annotations

from pathlib import Path

from decepticon.orchestrator import OrchestratorPhase, OrchestratorState, VaccineOrchestrator
from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    ReAttackOutcome,
    VerificationResult,
)

# ── OrchestratorState defaults ────────────────────────────────────────────────


def test_orchestrator_state_defaults() -> None:
    state = OrchestratorState()
    assert state.phase == OrchestratorPhase.ATTACK
    assert state.iteration == 0
    assert state.max_iterations == 10
    assert state.findings_discovered == []
    assert state.findings_processed == []
    assert state.defenses_applied == []
    assert state.verification_results == []


# ── OrchestratorPhase values ──────────────────────────────────────────────────


def test_orchestrator_phase_values() -> None:
    assert OrchestratorPhase.ATTACK == "attack"
    assert OrchestratorPhase.BRIEF_GENERATION == "brief_generation"
    assert OrchestratorPhase.DEFENSE == "defense"
    assert OrchestratorPhase.VERIFICATION == "verification"
    assert OrchestratorPhase.COMPLETE == "complete"
    assert len(OrchestratorPhase) == 5


# ── _scan_findings ────────────────────────────────────────────────────────────


def test_scan_findings(tmp_path: Path) -> None:
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir()
    (findings_dir / "FIND-001.md").write_text("# Finding 1", encoding="utf-8")
    (findings_dir / "FIND-002.md").write_text("# Finding 2", encoding="utf-8")
    # This file should NOT be picked up
    (findings_dir / "notes.md").write_text("# Notes", encoding="utf-8")

    orchestrator = VaccineOrchestrator(tmp_path)
    refs = orchestrator._scan_findings()

    assert refs == ["FIND-001", "FIND-002"]


def test_scan_findings_empty(tmp_path: Path) -> None:
    orchestrator = VaccineOrchestrator(tmp_path)
    refs = orchestrator._scan_findings()
    assert refs == []


# ── _generate_brief ───────────────────────────────────────────────────────────


def test_generate_brief(tmp_path: Path) -> None:
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir()
    (findings_dir / "FIND-001.md").write_text(
        "# Exposed SSH Service\n\n"
        "**Severity**: high\n\n"
        "**Attack Vector**: SSH brute-force over open port tcp/22\n\n"
        "**Affected**: 10.0.0.1\n\n"
        "## Evidence\n\nPort 22 open and accepting connections.\n",
        encoding="utf-8",
    )

    orchestrator = VaccineOrchestrator(tmp_path)
    brief = orchestrator._generate_brief("FIND-001")

    assert brief is not None
    assert brief.finding_ref == "FIND-001"
    assert brief.finding_title == "Exposed SSH Service"
    assert brief.severity == "high"
    # Should have inferred at least one recommendation from the attack vector text
    assert len(brief.recommended_actions) >= 1


def test_generate_brief_missing_file(tmp_path: Path) -> None:
    orchestrator = VaccineOrchestrator(tmp_path)
    brief = orchestrator._generate_brief("FIND-999")
    assert brief is None


# ── save + load state ─────────────────────────────────────────────────────────


def test_save_and_load_state(tmp_path: Path) -> None:
    state = OrchestratorState(
        phase=OrchestratorPhase.VERIFICATION,
        iteration=3,
        max_iterations=5,
        findings_discovered=["FIND-001", "FIND-002"],
        findings_processed=["FIND-001"],
    )
    orchestrator = VaccineOrchestrator(tmp_path, state)
    orchestrator._save_state()

    # Load back via a fresh orchestrator reading the persisted file
    loaded_state = orchestrator._load_state()
    assert loaded_state is not None
    assert loaded_state.phase == OrchestratorPhase.VERIFICATION
    assert loaded_state.iteration == 3
    assert loaded_state.max_iterations == 5
    assert loaded_state.findings_discovered == ["FIND-001", "FIND-002"]
    assert loaded_state.findings_processed == ["FIND-001"]


# ── run with no findings ──────────────────────────────────────────────────────


async def test_run_no_findings(tmp_path: Path) -> None:
    """With no findings directory, the loop should complete in one iteration."""
    orchestrator = VaccineOrchestrator(tmp_path)
    final_state = await orchestrator.run()

    assert final_state.phase == OrchestratorPhase.COMPLETE
    assert final_state.findings_processed == []
    assert final_state.iteration == 1


# ── summary property ──────────────────────────────────────────────────────────


def test_summary_property(tmp_path: Path) -> None:
    action_result = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/22",
        success=True,
        message="Port blocked",
    )
    blocked_vr = VerificationResult(
        finding_ref="FIND-001",
        defense_actions_applied=[action_result],
        re_attack_outcome=ReAttackOutcome.BLOCKED,
    )
    failed_vr = VerificationResult(
        finding_ref="FIND-002",
        re_attack_outcome=ReAttackOutcome.PASSED,
    )

    state = OrchestratorState(
        phase=OrchestratorPhase.COMPLETE,
        iteration=2,
        max_iterations=10,
        findings_discovered=["FIND-001", "FIND-002"],
        findings_processed=["FIND-001", "FIND-002"],
        verification_results=[blocked_vr, failed_vr],
    )
    orchestrator = VaccineOrchestrator(tmp_path, state)
    summary = orchestrator.summary

    assert summary["phase"] == OrchestratorPhase.COMPLETE
    assert summary["iteration"] == 2
    assert summary["max_iterations"] == 10
    assert summary["findings_discovered"] == 2
    assert summary["findings_processed"] == 2
    assert summary["verified"] == 1
    assert summary["failed"] == 1
    assert "started_at" in summary
