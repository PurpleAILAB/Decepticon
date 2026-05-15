"""Tests for the headless CI scan gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from decepticon.cicd.scan import evaluate_gate, load_findings, main

# ── load_findings ────────────────────────────────────────────────


def test_load_findings_list(tmp_path: Path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps([{"id": "1", "severity": "high"}]))
    assert load_findings(p) == [{"id": "1", "severity": "high"}]


def test_load_findings_envelope(tmp_path: Path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"findings": [{"id": "1"}]}))
    assert load_findings(p) == [{"id": "1"}]


def test_load_findings_missing_file_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="not found"):
        load_findings(tmp_path / "nope.json")


def test_load_findings_bad_json_raises(tmp_path: Path):
    p = tmp_path / "f.json"
    p.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_findings(p)


def test_load_findings_wrong_shape_raises(tmp_path: Path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps("a string"))
    with pytest.raises(ValueError, match="must be a JSON list"):
        load_findings(p)


def test_load_findings_drops_non_dict_entries(tmp_path: Path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps([{"id": "1"}, "junk", 42]))
    assert load_findings(p) == [{"id": "1"}]


# ── evaluate_gate ────────────────────────────────────────────────


def test_gate_blocks_in_scope_finding():
    findings = [{"id": "1", "severity": "high", "file": "decepticon/a.py"}]
    gate = evaluate_gate(findings, ["decepticon/a.py"], fail_on="low")
    assert gate["failed"] is True
    assert len(gate["blocking"]) == 1


def test_gate_ignores_out_of_scope_finding():
    findings = [{"id": "1", "severity": "high", "file": "other/b.py"}]
    gate = evaluate_gate(findings, ["decepticon/a.py"], fail_on="low")
    assert gate["failed"] is False
    assert len(gate["ignored"]) == 1


def test_gate_respects_severity_threshold():
    findings = [{"id": "1", "severity": "low", "file": "a.py"}]
    gate = evaluate_gate(findings, ["a.py"], fail_on="high")
    assert gate["failed"] is False  # low < high threshold


def test_gate_no_scope_counts_everything():
    findings = [{"id": "1", "severity": "critical", "file": "anywhere.py"}]
    gate = evaluate_gate(findings, [], fail_on="low", scope_to_diff=False)
    assert gate["failed"] is True


def test_gate_reads_severity_and_path_from_props():
    findings = [{"id": "1", "props": {"severity": "critical", "path": "x.py"}}]
    gate = evaluate_gate(findings, ["x.py"], fail_on="high")
    assert gate["failed"] is True


def test_gate_unknown_severity_treated_as_info():
    findings = [{"id": "1", "severity": "weird", "file": "a.py"}]
    gate = evaluate_gate(findings, ["a.py"], fail_on="low")
    # "weird" → rank 0 < low(1) → not blocking
    assert gate["failed"] is False


def test_gate_empty_findings_passes():
    gate = evaluate_gate([], ["a.py"], fail_on="low")
    assert gate["failed"] is False
    assert gate["blocking"] == []


# ── main() exit codes ────────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=r, check=True)
    (r / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=r, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=r, check=True)
    (r / "app.py").write_text("x = 1\nimport os\nos.system(input())\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "vuln"], cwd=r, check=True)
    return r


def test_main_check_only_returns_zero(git_repo: Path, capsys):
    rc = main(["--diff-base", "main", "--repo", str(git_repo), "--check-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "app.py" in out
    assert "check-only" in out


def test_main_gate_fails_on_in_scope_finding(git_repo: Path, tmp_path: Path):
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps([{"id": "F1", "severity": "high", "title": "RCE", "file": "app.py"}])
    )
    rc = main(
        [
            "--diff-base",
            "main",
            "--repo",
            str(git_repo),
            "--findings",
            str(findings),
            "--fail-on",
            "medium",
        ]
    )
    assert rc == 1


def test_main_gate_passes_when_finding_out_of_scope(git_repo: Path, tmp_path: Path):
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps([{"id": "F1", "severity": "high", "title": "RCE", "file": "untouched.py"}])
    )
    rc = main(
        [
            "--diff-base",
            "main",
            "--repo",
            str(git_repo),
            "--findings",
            str(findings),
        ]
    )
    assert rc == 0


def test_main_requires_findings_without_check_only(git_repo: Path, capsys):
    rc = main(["--diff-base", "main", "--repo", str(git_repo)])
    assert rc == 2
    assert "findings is required" in capsys.readouterr().err


def test_main_bad_base_returns_2(git_repo: Path, capsys):
    rc = main(["--diff-base", "nonexistent", "--repo", str(git_repo), "--check-only"])
    assert rc == 2
    assert "error:" in capsys.readouterr().err


def test_module_runs_as_subprocess(git_repo: Path):
    """``python -m decepticon.cicd.scan`` is the GitHub Action entrypoint."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "decepticon.cicd.scan",
            "--diff-base",
            "main",
            "--repo",
            str(git_repo),
            "--check-only",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[3],
    )
    assert proc.returncode == 0, proc.stderr
    assert "Decepticon CI scan" in proc.stdout
