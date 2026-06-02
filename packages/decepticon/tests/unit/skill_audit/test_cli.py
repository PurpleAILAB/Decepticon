"""Tests for the corpus scanner + CLI rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.skill_audit.cli import (
    ExitCode,
    main,
    scan_corpus,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_corpus(tmp_path: Path) -> Path:
    """Replicate the /skills/standard/<phase>/<skill>/SKILL.md tree.

    Returns the corpus root, which the scanner is invoked against.
    """
    root = tmp_path / "skills"
    layout = {
        "standard/recon/clean": "clean.md",
        "standard/recon/missing-subdomain": "missing_subdomain.md",
        "standard/recon/bad-mitre": "bad_mitre.md",
        "standard/recon/no-attribution": "no_attribution.md",
        "standard/reporting/reporting-example": "reporting_skill.md",
    }
    for rel, fixture in layout.items():
        skill_dir = root / rel
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            (FIXTURES / fixture).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return root


def test_scan_corpus_walks_every_skill_md(tmp_path: Path) -> None:
    root = _make_corpus(tmp_path)
    report = scan_corpus(root)
    assert report.files_scanned == 5


def test_scan_corpus_reports_violations_per_file(tmp_path: Path) -> None:
    root = _make_corpus(tmp_path)
    report = scan_corpus(root)
    # Clean fixture: 0 violations; the three offensive-with-issues
    # fixtures: at least one violation each; the reporting fixture: 0.
    by_path = {v.path for v in report.violations}
    assert any("missing-subdomain" in p for p in by_path)
    assert any("bad-mitre" in p for p in by_path)
    assert any("no-attribution" in p for p in by_path)
    assert not any("/standard/reporting/reporting-example/SKILL.md" in p for p in by_path)
    assert not any("/standard/recon/clean/SKILL.md" in p for p in by_path)


def test_main_exits_zero_when_warn_mode_and_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    exit_code = main(["--root", str(root), "--mode", "warn"])
    assert exit_code == ExitCode.OK
    out = capsys.readouterr().out
    assert "R-missing-required" in out
    assert "R-bad-mitre-format" in out
    assert "R-no-attribution" in out


def test_main_exits_nonzero_when_strict_mode_and_violations(
    tmp_path: Path,
) -> None:
    root = _make_corpus(tmp_path)
    exit_code = main(["--root", str(root), "--mode", "strict"])
    assert exit_code == ExitCode.VIOLATIONS_FOUND


def test_main_exits_zero_in_strict_mode_with_clean_corpus(
    tmp_path: Path,
) -> None:
    root = tmp_path / "skills"
    (root / "standard" / "recon" / "clean").mkdir(parents=True)
    (root / "standard" / "recon" / "clean" / "SKILL.md").write_text(
        (FIXTURES / "clean.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    exit_code = main(["--root", str(root), "--mode", "strict"])
    assert exit_code == ExitCode.OK
