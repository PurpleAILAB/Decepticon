"""Unit tests for EnvironmentVerifier — environment-grounded vaccine verification."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable

from decepticon.core.env_verifier import EnvironmentVerifier
from decepticon.schemas.defense_brief import ReAttackOutcome
from decepticon.schemas.env_verification import (
    CheckPhase,
    EnvironmentSnapshot,
    PoCEvidence,
    TargetCheckResult,
    VerificationEvidence,
)
from decepticon.schemas.exploit_spec import (
    CommandOutputCheck,
    ExploitSpec,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def make_runner(
    poc_response: tuple[str, str, int] = ("PWNED root@target", "", 0),
    negative_response: tuple[str, str, int] = ("clean", "", 0),
    check_response: tuple[str, str, int] = ("matched", "", 0),
) -> Callable[[str], Awaitable[tuple[str, str, int]]]:
    """Build a deterministic mock PoCRunner that branches on command shape."""

    async def _run(command: str) -> tuple[str, str, int]:
        if "PWNED" in command or "exploit" in command.lower():
            return poc_response
        if "clean_request" in command or "noop" in command:
            return negative_response
        return check_response

    return _run


def make_spec(
    finding_ref: str = "FIND-001",
    success_patterns: list[str] | None = None,
    negative_command: str | None = None,
) -> ExploitSpec:
    return ExploitSpec(
        finding_ref=finding_ref,
        poc_command="curl -X POST exploit",
        success_patterns=success_patterns or ["PWNED"],
        negative_command=negative_command,
        target_checks=[
            CommandOutputCheck(
                command="echo matched",
                pattern="matched",
                expect_match=True,
            )
        ],
    )


# ── Test 1: Pre-defense exploit succeeds → PASSED, reward 0.0 ──────────────


async def test_pre_defense_exploit_passed(tmp_path: Path) -> None:
    runner = make_runner(poc_response=("PWNED root@target", "", 0))
    verifier = EnvironmentVerifier(tmp_path, runner)
    spec = make_spec()

    pre = await verifier.capture_state(spec, phase=CheckPhase.PRE_DEFENSE)
    # No POST snapshot pretend not yet defended; use pre as both
    evidence = await verifier.verify_blocked(spec, pre=None, post=pre)

    assert evidence.re_attack_outcome == ReAttackOutcome.PASSED
    assert "PWNED" in evidence.poc_evidence.success_signals_matched
    reward = verifier.compute_reward(evidence)
    assert reward.reward == 0.0
    assert reward.outcome == ReAttackOutcome.PASSED


# ── Test 2: Post-defense exploit fails → BLOCKED, reward 1.0 ───────────────


async def test_post_defense_exploit_blocked(tmp_path: Path) -> None:
    runner = make_runner(poc_response=("", "Permission denied", 1))
    verifier = EnvironmentVerifier(tmp_path, runner)
    spec = make_spec()

    post = await verifier.capture_state(spec, phase=CheckPhase.POST_DEFENSE)
    evidence = await verifier.verify_blocked(spec, pre=None, post=post)

    assert evidence.re_attack_outcome == ReAttackOutcome.BLOCKED
    assert evidence.poc_evidence.success_signals_matched == []
    reward = verifier.compute_reward(evidence)
    assert reward.reward == 1.0
    assert reward.outcome == ReAttackOutcome.BLOCKED


# ── Test 3: ZFP demotion → ERROR, reward 0.0 ───────────────────────────────


async def test_zfp_demotion_errors(tmp_path: Path) -> None:
    # Both PoC and negative control match success patterns — noise signal
    async def _run(command: str) -> tuple[str, str, int]:
        return ("PWNED everywhere", "", 0)

    verifier = EnvironmentVerifier(tmp_path, _run)
    spec = make_spec(negative_command="curl noop")

    post = await verifier.capture_state(spec, phase=CheckPhase.POST_DEFENSE)
    evidence = await verifier.verify_blocked(spec, pre=None, post=post)

    assert evidence.poc_evidence.zfp_demoted is True
    assert evidence.re_attack_outcome == ReAttackOutcome.ERROR
    reward = verifier.compute_reward(evidence)
    assert reward.reward == 0.0
    assert reward.zfp_demoted is True


# ── Test 4: PARTIAL outcome → reward 0.5 ───────────────────────────────────


async def test_partial_reward(tmp_path: Path) -> None:
    runner = make_runner()
    verifier = EnvironmentVerifier(tmp_path, runner)
    pre = EnvironmentSnapshot(
        finding_ref="FIND-002",
        phase=CheckPhase.PRE_DEFENSE,
        results=[
            TargetCheckResult(
                check_id="FIND-002-pre_defense-0",
                kind="command",
                phase=CheckPhase.PRE_DEFENSE,
                positive=True,
            ),
            TargetCheckResult(
                check_id="FIND-002-pre_defense-1",
                kind="command",
                phase=CheckPhase.PRE_DEFENSE,
                positive=True,
            ),
        ],
    )
    post = EnvironmentSnapshot(
        finding_ref="FIND-002",
        phase=CheckPhase.POST_DEFENSE,
        results=[
            TargetCheckResult(
                check_id="FIND-002-post_defense-0",
                kind="command",
                phase=CheckPhase.POST_DEFENSE,
                positive=False,
            ),
            TargetCheckResult(
                check_id="FIND-002-post_defense-1",
                kind="command",
                phase=CheckPhase.POST_DEFENSE,
                positive=True,
            ),
        ],
    )
    evidence = VerificationEvidence(
        finding_ref="FIND-002",
        pre_snapshot=pre,
        post_snapshot=post,
        poc_evidence=PoCEvidence(
            exit_code=0,
            success_signals_matched=["PWNED"],
            zfp_demoted=False,
            output_hash="abc123",
        ),
        re_attack_outcome=ReAttackOutcome.PARTIAL,
    )
    reward = verifier.compute_reward(evidence)
    assert reward.reward == 0.5
    assert reward.outcome == ReAttackOutcome.PARTIAL
    assert reward.blocked_checks == 1
    assert reward.total_checks == 2


# ── Test 5: persist_reward writes valid JSONL line ─────────────────────────


async def test_persist_reward_writes_jsonl(tmp_path: Path) -> None:
    runner = make_runner(poc_response=("", "Permission denied", 1))
    verifier = EnvironmentVerifier(tmp_path, runner)
    spec = make_spec()

    post = await verifier.capture_state(spec, phase=CheckPhase.POST_DEFENSE)
    evidence = await verifier.verify_blocked(spec, pre=None, post=post)
    reward = verifier.compute_reward(evidence)
    verifier.persist_reward(reward)

    rewards_path = tmp_path / "rlvr" / "rewards.jsonl"
    assert rewards_path.exists()
    lines = rewards_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["finding_ref"] == "FIND-001"
    assert parsed["reward"] == 1.0
    assert parsed["outcome"] == "blocked"

    # Append-only: second write produces a second line
    verifier.persist_reward(reward)
    lines2 = rewards_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 2
    json.loads(lines2[1])  # validates JSON


# ── Test 6: spec round-trip via load_spec ──────────────────────────────────


async def test_load_spec_roundtrip(tmp_path: Path) -> None:
    runner = make_runner()
    verifier = EnvironmentVerifier(tmp_path, runner)
    spec = make_spec("FIND-077")
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir(parents=True)
    (findings_dir / "FIND-077-exploit-spec.json").write_text(
        spec.model_dump_json(indent=2), encoding="utf-8"
    )
    loaded = verifier.load_spec("FIND-077")
    assert loaded is not None
    assert loaded.finding_ref == "FIND-077"
    assert loaded.success_patterns == ["PWNED"]


async def test_load_spec_missing_returns_none(tmp_path: Path) -> None:
    runner = make_runner()
    verifier = EnvironmentVerifier(tmp_path, runner)
    assert verifier.load_spec("FIND-NONE") is None


# ── Test 7: persist_snapshot + persist_evidence write to disk ──────────────


async def test_persistence_writes_snapshot_and_evidence(tmp_path: Path) -> None:
    runner = make_runner(poc_response=("", "blocked", 1))
    verifier = EnvironmentVerifier(tmp_path, runner)
    spec = make_spec()

    post = await verifier.capture_state(spec, phase=CheckPhase.POST_DEFENSE)
    verifier.persist_snapshot(post)
    snap_path = tmp_path / "verification" / "FIND-001-post_defense-snapshot.json"
    assert snap_path.exists()

    evidence = await verifier.verify_blocked(spec, pre=None, post=post)
    verifier.persist_evidence(evidence)
    evidence_path = tmp_path / "verification" / "FIND-001-evidence.json"
    assert evidence_path.exists()
    parsed = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert parsed["finding_ref"] == "FIND-001"
