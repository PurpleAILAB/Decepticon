"""Workspace scaffold behavior for engagement document saves."""

from __future__ import annotations

from pathlib import Path

from decepticon.core.schemas import (
    CONOPS,
    OPPLAN,
    DeconflictionPlan,
    EngagementBundle,
    EngagementType,
    RoE,
)


def _bundle() -> EngagementBundle:
    return EngagementBundle(
        roe=RoE(
            engagement_name="test-engagement",
            client="Test Client",
            start_date="2026-05-04",
            end_date="2026-05-05",
            engagement_type=EngagementType.EXTERNAL,
            testing_window="24/7",
        ),
        conops=CONOPS(
            engagement_name="test-engagement",
            executive_summary="Test engagement.",
        ),
        opplan=OPPLAN(
            engagement_name="test-engagement",
            threat_profile="test",
            objectives=[],
        ),
        deconfliction=DeconflictionPlan(engagement_name="test-engagement"),
    )


def test_engagement_bundle_save_does_not_precreate_artifact_scaffold(tmp_path: Path) -> None:
    files = _bundle().save(str(tmp_path))

    assert set(files) == {"roe", "conops", "opplan", "deconfliction"}
    assert (tmp_path / "plan" / "roe.json").is_file()
    assert (tmp_path / "plan" / "conops.json").is_file()
    assert (tmp_path / "plan" / "opplan.json").is_file()
    assert (tmp_path / "plan" / "deconfliction.json").is_file()

    for artifact in (
        "recon",
        "exploit",
        "post-exploit",
        "findings",
        "report",
        "timeline.jsonl",
    ):
        assert not (tmp_path / artifact).exists()
