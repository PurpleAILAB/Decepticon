from __future__ import annotations

from pathlib import Path

from decepticon.capabilities.evidence import validate_evidence, validate_evidence_files


def test_evidence_requires_positive_and_baseline_signals() -> None:
    result = validate_evidence(
        "HTTP 200\nsecret=decepticon-proof",
        "HTTP 200\nwelcome back",
        success_patterns=[r"secret=decepticon-proof"],
        negative_patterns=[r"welcome back"],
    )

    assert result.validated is True
    assert result.success_matches == (r"secret=decepticon-proof",)
    assert result.negative_matches == (r"welcome back",)


def test_evidence_rejects_signal_that_also_appears_in_negative_control() -> None:
    result = validate_evidence(
        "secret=decepticon-proof",
        "baseline secret=decepticon-proof",
        success_patterns=[r"secret=decepticon-proof"],
        negative_patterns=[r"baseline"],
    )

    assert result.validated is False
    assert result.noise_matches == (r"secret=decepticon-proof",)
    assert "negative control also matched" in result.reason


def test_evidence_rejects_invalid_regex_instead_of_falling_back_to_substring() -> None:
    result = validate_evidence(
        "proof",
        "baseline",
        success_patterns=["[unclosed"],
        negative_patterns=["baseline"],
    )

    assert result.validated is False
    assert "invalid" in result.reason


def test_evidence_file_paths_are_confined_to_workspace(tmp_path: Path) -> None:
    result = validate_evidence_files(
        tmp_path,
        success_path="../outside.txt",
        negative_path="baseline.txt",
        success_patterns=["proof"],
        negative_patterns=["baseline"],
    )

    assert result.validated is False
    assert result.errors == ("evidence path escapes the workspace",)


def test_evidence_files_must_be_distinct(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("proof baseline", encoding="utf-8")

    result = validate_evidence_files(
        tmp_path,
        success_path="evidence.txt",
        negative_path="evidence.txt",
        success_patterns=["proof"],
        negative_patterns=["baseline"],
    )

    assert result.validated is False
    assert "must be distinct" in result.reason
