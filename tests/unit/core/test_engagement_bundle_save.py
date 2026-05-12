"""Unit tests for EngagementBundle.save().

Verifies that save() uses atomic writes, writes the .bundle_complete marker
last, and leaves no temp artifacts behind on completion.

These tests exercise the local-filesystem path only (EngagementBundle.save is
the fixture/test helper, not the live Soundwave flow).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from decepticon.core.schemas import (
    CONOPS,
    OPPLAN,
    DeconflictionPlan,
    EngagementBundle,
    EngagementType,
    RoE,
    ScopeEntry,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _minimal_bundle() -> EngagementBundle:
    roe = RoE(
        engagement_name="test-eng",
        client="Acme Corp",
        start_date="2026-01-01",
        end_date="2026-01-31",
        engagement_type=EngagementType.EXTERNAL,
        testing_window="Mon-Fri 09:00-18:00 UTC",
        in_scope=[ScopeEntry(target="example.com", type="domain")],
    )
    conops = CONOPS(
        engagement_name="test-eng",
        executive_summary="Test engagement.",
    )
    opplan = OPPLAN(
        engagement_name="test-eng",
        threat_profile="Generic external attacker.",
        objectives=[],
    )
    deconfliction = DeconflictionPlan(
        engagement_name="test-eng",
    )
    return EngagementBundle(roe=roe, conops=conops, opplan=opplan, deconfliction=deconfliction)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_save_writes_all_four_documents(tmp_path: Path) -> None:
    bundle = _minimal_bundle()
    files = bundle.save(str(tmp_path))

    assert set(files.keys()) == {"roe", "conops", "opplan", "deconfliction"}
    for name, path in files.items():
        assert Path(path).exists(), f"{name}.json missing"
        data = json.loads(Path(path).read_text())
        assert isinstance(data, dict)


def test_save_writes_completion_marker_last(tmp_path: Path) -> None:
    """The .bundle_complete marker must have a mtime >= every plan doc."""
    bundle = _minimal_bundle()
    bundle.save(str(tmp_path))

    plan_dir = tmp_path / "plan"
    marker = plan_dir / ".bundle_complete"
    assert marker.exists(), ".bundle_complete not written"

    marker_mtime = marker.stat().st_mtime
    for doc in ["roe.json", "conops.json", "opplan.json", "deconfliction.json"]:
        doc_mtime = (plan_dir / doc).stat().st_mtime
        assert marker_mtime >= doc_mtime, (
            f".bundle_complete mtime ({marker_mtime}) < {doc} mtime ({doc_mtime})"
        )


def test_save_no_tmp_artifacts_remain(tmp_path: Path) -> None:
    bundle = _minimal_bundle()
    bundle.save(str(tmp_path))

    tmp_files = list((tmp_path / "plan").glob("*.tmp"))
    assert not tmp_files, f"temp artifacts remain: {tmp_files}"


def test_save_marker_is_final_replace_call(tmp_path: Path) -> None:
    """os.replace calls should end with the marker replace (atomicity)."""
    replace_calls: list[tuple] = []

    orig_replace = os.replace

    def tracking_replace(src: str, dst: str) -> None:
        replace_calls.append((src, dst))
        orig_replace(src, dst)

    with patch("os.replace", side_effect=tracking_replace):
        bundle = _minimal_bundle()
        bundle.save(str(tmp_path))

    assert replace_calls, "os.replace never called"
    last_dst = str(replace_calls[-1][1])
    assert last_dst.endswith(".bundle_complete"), (
        f"last os.replace destination should be .bundle_complete, got: {last_dst}"
    )


def test_save_unlinks_prior_marker_before_writing(tmp_path: Path) -> None:
    """A pre-existing stale marker must be removed before the new one is written."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    stale_marker = plan_dir / ".bundle_complete"
    stale_marker.write_bytes(b"stale")

    bundle = _minimal_bundle()
    bundle.save(str(tmp_path))

    new_marker = plan_dir / ".bundle_complete"
    assert new_marker.exists()
    content = json.loads(new_marker.read_bytes())
    assert content.get("schema_version") == 1, "marker should contain schema_version:1"


def test_save_partial_failure_leaves_no_marker(tmp_path: Path) -> None:
    """If the marker write raises, no marker should survive."""
    import decepticon.core._atomic as atomic_mod
    from decepticon.core._atomic import atomic_write_bytes as _real_write

    def failing_on_marker(path: Path, data: bytes) -> None:
        if path.name == ".bundle_complete":
            raise OSError("injected failure")
        _real_write(path, data)

    with patch.object(atomic_mod, "atomic_write_bytes", side_effect=failing_on_marker):
        bundle = _minimal_bundle()
        with pytest.raises(OSError, match="injected failure"):
            bundle.save(str(tmp_path))

    marker = tmp_path / "plan" / ".bundle_complete"
    assert not marker.exists(), ".bundle_complete must not exist after partial failure"
