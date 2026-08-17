"""Deterministic capability scorecards for held-out evaluations."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from decepticon.capabilities.contracts import CapabilityLane


@dataclass(frozen=True)
class EvaluationRecord:
    """One completed capability evaluation, including rejected hypotheses."""

    lane: CapabilityLane
    verified: bool
    duration_seconds: float
    cost_usd: float | None = None
    root_cause_id: str | None = None
    visible_to_user: bool = False


@dataclass(frozen=True)
class LaneScorecard:
    """Metrics that distinguish validated capability from raw finding volume."""

    lane: CapabilityLane
    attempts: int
    validated: int
    validated_rate: float
    visible_validated: int
    visible_validated_rate: float
    unique_root_causes: int
    median_duration_seconds: float
    total_cost_usd: float | None


def build_scorecards(records: list[EvaluationRecord]) -> list[LaneScorecard]:
    """Aggregate records by lane without hiding missing cost attribution."""
    grouped: dict[CapabilityLane, list[EvaluationRecord]] = defaultdict(list)
    for record in records:
        if record.duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative")
        if record.cost_usd is not None and record.cost_usd < 0:
            raise ValueError("cost_usd must not be negative")
        grouped[record.lane].append(record)

    scorecards: list[LaneScorecard] = []
    for lane in sorted(grouped, key=str):
        lane_records = grouped[lane]
        attempts = len(lane_records)
        validated = sum(record.verified for record in lane_records)
        visible_validated = sum(
            record.verified and record.visible_to_user for record in lane_records
        )
        known_costs = [record.cost_usd for record in lane_records if record.cost_usd is not None]
        scorecards.append(
            LaneScorecard(
                lane=lane,
                attempts=attempts,
                validated=validated,
                validated_rate=validated / attempts,
                visible_validated=visible_validated,
                visible_validated_rate=visible_validated / attempts,
                unique_root_causes=len(
                    {
                        record.root_cause_id
                        for record in lane_records
                        if record.verified and record.root_cause_id
                    }
                ),
                median_duration_seconds=float(
                    median(record.duration_seconds for record in lane_records)
                ),
                total_cost_usd=round(sum(known_costs), 6) if len(known_costs) == attempts else None,
            )
        )
    return scorecards


def load_evaluation_records(path: Path) -> list[EvaluationRecord]:
    """Load explicit, schema-checked held-out evaluation records from JSONL."""
    records: list[EvaluationRecord] = []
    allowed = {
        "lane",
        "verified",
        "duration_seconds",
        "cost_usd",
        "root_cause_id",
        "visible_to_user",
    }
    required = {"lane", "verified", "duration_seconds", "visible_to_user"}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_number}: record must be an object")
        unknown = sorted(set(item) - allowed)
        missing = sorted(required - set(item))
        if unknown or missing:
            raise ValueError(
                f"{path}:{line_number}: unknown fields {unknown}; missing fields {missing}"
            )
        if not isinstance(item["verified"], bool) or not isinstance(item["visible_to_user"], bool):
            raise ValueError(f"{path}:{line_number}: verification fields must be booleans")
        if not isinstance(item["duration_seconds"], (int, float)) or isinstance(
            item["duration_seconds"], bool
        ):
            raise ValueError(f"{path}:{line_number}: duration_seconds must be numeric")
        cost = item.get("cost_usd")
        if not isinstance(cost, (int, float, type(None))) or isinstance(cost, bool):
            raise ValueError(f"{path}:{line_number}: cost_usd must be numeric or null")
        root_cause_id = item.get("root_cause_id")
        if not isinstance(root_cause_id, (str, type(None))):
            raise ValueError(f"{path}:{line_number}: root_cause_id must be a string or null")
        try:
            lane = CapabilityLane(item["lane"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: unknown capability lane") from exc
        records.append(
            EvaluationRecord(
                lane=lane,
                verified=item["verified"],
                duration_seconds=float(item["duration_seconds"]),
                cost_usd=None if cost is None else float(cost),
                root_cause_id=root_cause_id,
                visible_to_user=item["visible_to_user"],
            )
        )
    return records
