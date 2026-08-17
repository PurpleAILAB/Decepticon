from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.capabilities.contracts import CapabilityLane
from decepticon.capabilities.scorecards import (
    EvaluationRecord,
    build_scorecards,
    load_evaluation_records,
)


def test_scorecards_preserve_unknown_cost_and_count_unique_verified_root_causes() -> None:
    scorecards = build_scorecards(
        [
            EvaluationRecord(CapabilityLane.WEB3, True, 3.0, 0.1, "root-a", True),
            EvaluationRecord(CapabilityLane.WEB3, False, 1.0, None, "root-b", False),
            EvaluationRecord(CapabilityLane.WEB3, True, 5.0, 0.2, "root-a", False),
        ]
    )

    assert len(scorecards) == 1
    scorecard = scorecards[0]
    assert scorecard.attempts == 3
    assert scorecard.validated == 2
    assert scorecard.validated_rate == pytest.approx(2 / 3)
    assert scorecard.visible_validated == 1
    assert scorecard.visible_validated_rate == pytest.approx(1 / 3)
    assert scorecard.unique_root_causes == 1
    assert scorecard.median_duration_seconds == 3.0
    assert scorecard.total_cost_usd is None


def test_held_out_fixture_covers_each_capability_lane() -> None:
    fixture = Path(__file__).parents[2] / "fixtures" / "capabilities" / "held-out.jsonl"

    records = load_evaluation_records(fixture)

    assert {record.lane for record in records} == set(CapabilityLane)
    assert all(record.visible_to_user for record in records)
    assert {scorecard.lane for scorecard in build_scorecards(records)} == set(CapabilityLane)


def test_scorecards_reject_negative_measurements() -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        build_scorecards([EvaluationRecord(CapabilityLane.WEB, True, -1.0)])
