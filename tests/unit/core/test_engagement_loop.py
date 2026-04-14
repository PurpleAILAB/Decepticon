"""Unit tests for decepticon.core.engagement_loop.EngagementLoop."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from decepticon.core.engagement import EngagementConfig, EngagementState
from decepticon.core.engagement_loop import EngagementLoop
from decepticon.core.schemas import (
    OPPLAN,
    Objective,
    ObjectivePhase,
    ObjectiveStatus,
    OpsecLevel,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_config(workspace: Path) -> EngagementConfig:
    return EngagementConfig(
        target="10.0.0.1",
        langgraph_url="http://localhost:8123",
        workspace=workspace,
    )


def _make_objective(
    obj_id: str = "OBJ-001",
    phase: ObjectivePhase = ObjectivePhase.RECON,
    priority: int = 1,
    status: ObjectiveStatus = ObjectiveStatus.PENDING,
    blocked_by: list[str] | None = None,
) -> Objective:
    return Objective(
        id=obj_id,
        phase=phase,
        title=f"Test objective {obj_id}",
        description="A test objective",
        acceptance_criteria=["criterion A"],
        priority=priority,
        status=status,
        opsec=OpsecLevel.STANDARD,
        blocked_by=blocked_by or [],
    )


def _write_opplan(workspace: Path, objectives: list[Objective] | None = None) -> None:
    """Write a minimal OPPLAN file so the engagement loop can start."""
    if objectives is None:
        objectives = [_make_objective()]
    plan_dir = workspace / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    opplan = OPPLAN(
        engagement_name="test",
        threat_profile="unit-test",
        objectives=objectives,
    )
    (plan_dir / "opplan.json").write_text(opplan.model_dump_json(), encoding="utf-8")


# ── _select_agent ─────────────────────────────────────────────────────────────


def test_select_agent_recon(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    obj = _make_objective(phase=ObjectivePhase.RECON)
    assert loop._select_agent(obj) == "recon"


def test_select_agent_exploit(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    obj = _make_objective(phase=ObjectivePhase.INITIAL_ACCESS)
    assert loop._select_agent(obj) == "exploit"


def test_select_agent_default(tmp_path: Path) -> None:
    """An objective whose phase is not in agent_selection falls back to 'recon'."""
    config = _make_config(tmp_path)
    # Remove all entries so every lookup misses
    config.agent_selection.clear()
    loop = EngagementLoop(tmp_path, config)
    obj = _make_objective(phase=ObjectivePhase.RECON)
    assert loop._select_agent(obj) == "recon"


# ── _next_pending_objective ───────────────────────────────────────────────────


def test_next_pending_objective(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    loop._state = EngagementState()
    loop._opplan = OPPLAN(
        engagement_name="test",
        threat_profile="APT test actor",
        objectives=[
            _make_objective("OBJ-003", priority=3),
            _make_objective("OBJ-001", priority=1),
            _make_objective("OBJ-002", priority=2),
        ],
    )
    result = loop._next_pending_objective()
    assert result is not None
    assert result.id == "OBJ-001"


def test_next_pending_objective_respects_blocked_by(tmp_path: Path) -> None:
    """An objective whose dependency is not yet completed must be skipped."""
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    loop._state = EngagementState(objectives_completed=[])  # OBJ-001 not completed
    loop._opplan = OPPLAN(
        engagement_name="test",
        threat_profile="APT test actor",
        objectives=[
            _make_objective("OBJ-001", priority=1, status=ObjectiveStatus.IN_PROGRESS),
            _make_objective("OBJ-002", priority=2, blocked_by=["OBJ-001"]),
        ],
    )
    result = loop._next_pending_objective()
    # OBJ-001 is not PENDING; OBJ-002 is blocked by OBJ-001 which isn't completed
    assert result is None


def test_next_pending_objective_none_when_all_done(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    loop._state = EngagementState()
    loop._opplan = OPPLAN(
        engagement_name="test",
        threat_profile="APT test actor",
        objectives=[
            _make_objective("OBJ-001", status=ObjectiveStatus.COMPLETED),
            _make_objective("OBJ-002", status=ObjectiveStatus.BLOCKED),
        ],
    )
    result = loop._next_pending_objective()
    assert result is None


# ── _parse_objective_result ───────────────────────────────────────────────────


def test_parse_objective_result_passed(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    obj = _make_objective()
    start = time.time()
    result = loop._parse_objective_result(
        "OBJECTIVE PASSED — port 22 found open.", obj, "recon", start
    )
    assert result.outcome == "PASSED"
    assert result.objective_id == "OBJ-001"
    assert result.agent_used == "recon"


def test_parse_objective_result_blocked(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    obj = _make_objective()
    start = time.time()
    result = loop._parse_objective_result(
        "OBJECTIVE BLOCKED — target is unreachable.", obj, "recon", start
    )
    assert result.outcome == "BLOCKED"


def test_parse_objective_result_finds_findings(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    obj = _make_objective()
    start = time.time()
    response = "OBJECTIVE PASSED. Wrote FIND-001 and FIND-002. Also referenced FIND-001 again."
    result = loop._parse_objective_result(response, obj, "recon", start)
    # FIND-001 appears twice but must be deduplicated; order preserved
    assert result.findings_produced == ["FIND-001", "FIND-002"]


# ── _build_attack_prompt ──────────────────────────────────────────────────────


def test_build_attack_prompt_contains_objective(tmp_path: Path) -> None:
    loop = EngagementLoop(tmp_path, _make_config(tmp_path))
    loop._state = EngagementState(iteration=1)
    obj = _make_objective(obj_id="OBJ-007", phase=ObjectivePhase.RECON)
    obj.title = "Enumerate open ports"

    prompt = loop._build_attack_prompt(obj)

    assert "OBJ-007" in prompt
    assert "Enumerate open ports" in prompt
    assert "OBJECTIVE PASSED" in prompt or "OBJECTIVE PASSED" in prompt
    # Confirm the objective phase appears
    assert "recon" in prompt


# ── interrupt saves state ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interrupt_saves_state(tmp_path: Path) -> None:
    """KeyboardInterrupt during the loop must persist state to disk."""
    _write_opplan(tmp_path)
    config = _make_config(tmp_path)
    loop = EngagementLoop(tmp_path, config)

    # Patch _run_attack_phase to raise KeyboardInterrupt immediately
    async def _raise_interrupt() -> None:
        raise KeyboardInterrupt

    with patch.object(loop, "_run_attack_phase", side_effect=_raise_interrupt):
        with pytest.raises(KeyboardInterrupt):
            await loop.run()

    # State file must exist after the interrupt
    state_file = tmp_path / ".engagement-state.json"
    assert state_file.exists(), "State file was not written on KeyboardInterrupt"

    loaded = EngagementState.load(tmp_path)
    assert loaded is not None
    assert loaded.target == "10.0.0.1"
