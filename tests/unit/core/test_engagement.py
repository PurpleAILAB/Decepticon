"""Unit tests for decepticon.core.engagement models."""

from __future__ import annotations

from pathlib import Path

from decepticon.core.engagement import (
    EngagementConfig,
    EngagementPhase,
    EngagementState,
    IterationResult,
    VaccineMode,
)

# ── EngagementPhase ───────────────────────────────────────────────────────────


def test_engagement_phase_values() -> None:
    assert EngagementPhase.PLANNING == "planning"
    assert EngagementPhase.ATTACK == "attack"
    assert EngagementPhase.VACCINE == "vaccine"
    assert EngagementPhase.COMPLETE == "complete"
    assert len(EngagementPhase) == 4


# ── VaccineMode ───────────────────────────────────────────────────────────────


def test_vaccine_mode_values() -> None:
    assert VaccineMode.BATCH == "batch"
    assert VaccineMode.IMMEDIATE == "immediate"
    assert len(VaccineMode) == 2


# ── EngagementConfig ──────────────────────────────────────────────────────────


def test_engagement_config_defaults() -> None:
    config = EngagementConfig(target="10.0.0.0/24")
    assert config.target == "10.0.0.0/24"
    assert config.max_iterations == 50
    assert config.vaccine_mode == VaccineMode.BATCH
    assert config.langgraph_url == "http://localhost:8123"
    assert config.workspace == Path("/workspace")


def test_engagement_config_agent_selection() -> None:
    config = EngagementConfig(target="example.com")
    mapping = config.agent_selection
    # All five ObjectivePhase values must have a mapped agent
    for phase in ("recon", "initial-access", "post-exploit", "c2", "exfiltration"):
        assert phase in mapping, f"Phase '{phase}' missing from agent_selection"
    assert mapping["recon"] == "recon"
    assert mapping["initial-access"] == "exploit"
    assert mapping["post-exploit"] == "postexploit"
    assert mapping["c2"] == "postexploit"
    assert mapping["exfiltration"] == "postexploit"


# ── EngagementState defaults ──────────────────────────────────────────────────


def test_engagement_state_defaults() -> None:
    state = EngagementState()
    assert state.phase == EngagementPhase.PLANNING
    assert state.iteration == 0
    assert state.max_iterations == 50
    assert state.current_objective_id is None
    assert state.objectives_completed == []
    assert state.objectives_blocked == []
    assert state.findings_discovered == []
    assert state.iteration_history == []
    assert state.workspace == "/workspace"
    assert state.target == ""
    assert state.resumed_at is None


# ── EngagementState save / load ───────────────────────────────────────────────


def test_engagement_state_save_load(tmp_path: Path) -> None:
    state = EngagementState(
        phase=EngagementPhase.ATTACK,
        iteration=3,
        max_iterations=20,
        target="192.168.1.0/24",
        objectives_completed=["OBJ-001"],
        findings_discovered=["FIND-001", "FIND-002"],
    )
    state.save(tmp_path)

    loaded = EngagementState.load(tmp_path)
    assert loaded is not None
    assert loaded.phase == EngagementPhase.ATTACK
    assert loaded.iteration == 3
    assert loaded.max_iterations == 20
    assert loaded.target == "192.168.1.0/24"
    assert loaded.objectives_completed == ["OBJ-001"]
    assert loaded.findings_discovered == ["FIND-001", "FIND-002"]


def test_engagement_state_load_missing(tmp_path: Path) -> None:
    result = EngagementState.load(tmp_path)
    assert result is None


# ── EngagementState.is_complete ───────────────────────────────────────────────


def test_engagement_state_is_complete_by_iterations() -> None:
    state = EngagementState(iteration=50, max_iterations=50)
    assert state.is_complete is True

    state_below = EngagementState(iteration=49, max_iterations=50)
    assert state_below.is_complete is False


def test_engagement_state_is_complete_by_phase() -> None:
    state = EngagementState(phase=EngagementPhase.COMPLETE, iteration=0, max_iterations=50)
    assert state.is_complete is True


# ── EngagementState.summary ───────────────────────────────────────────────────


def test_engagement_state_summary() -> None:
    state = EngagementState(
        phase=EngagementPhase.ATTACK,
        iteration=5,
        max_iterations=50,
        objectives_completed=["OBJ-001", "OBJ-002"],
        objectives_blocked=["OBJ-003"],
        findings_discovered=["FIND-001"],
    )
    summary = state.summary

    assert summary["phase"] == EngagementPhase.ATTACK
    assert summary["iteration"] == 5
    assert summary["max_iterations"] == 50
    assert summary["objectives_completed"] == 2
    assert summary["objectives_blocked"] == 1
    assert summary["total_processed"] == 3
    assert summary["findings_discovered"] == 1
    assert "is_complete" in summary


# ── IterationResult ───────────────────────────────────────────────────────────


def test_iteration_result_model() -> None:
    result = IterationResult(
        objective_id="OBJ-001",
        agent_used="recon",
        outcome="PASSED",
        findings_produced=["FIND-001"],
        duration_seconds=12.5,
    )
    assert result.objective_id == "OBJ-001"
    assert result.agent_used == "recon"
    assert result.outcome == "PASSED"
    assert result.findings_produced == ["FIND-001"]
    assert result.duration_seconds == 12.5
    assert result.error is None
