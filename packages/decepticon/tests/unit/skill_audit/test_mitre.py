"""Tests for MITRE ID format validation."""

from __future__ import annotations

import pytest

from decepticon.skill_audit.mitre import (
    MitreMatrix,
    classify_mitre_id,
    coerce_mitre_list,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("T1190", MitreMatrix.ENTERPRISE_OR_MOBILE),
        ("T1595.001", MitreMatrix.ENTERPRISE_OR_MOBILE),
        ("T0800", MitreMatrix.ICS),
        ("T0830.001", MitreMatrix.ICS),
        ("AML.T0043", MitreMatrix.ATLAS),
        ("AML.T0043.001", MitreMatrix.ATLAS),
    ],
)
def test_classify_mitre_id_accepts_valid_formats(raw: str, expected: MitreMatrix) -> None:
    assert classify_mitre_id(raw) is expected


@pytest.mark.parametrize(
    "bad",
    [
        "TA0001",  # tactic ID, not a technique
        "TA0008",
        "defense-evasion-validation",
        "T19",  # too short
        "T19000",  # too long
        "T1595.00a",  # non-digit sub
        "AML.T1190 stuff",
        "",
        "   ",
    ],
)
def test_classify_mitre_id_rejects_invalid_formats(bad: str) -> None:
    assert classify_mitre_id(bad) is None


def test_coerce_mitre_list_from_yaml_list() -> None:
    assert coerce_mitre_list(["T1190", "T1595.001"]) == [
        "T1190",
        "T1595.001",
    ]


def test_coerce_mitre_list_from_csv_string() -> None:
    assert coerce_mitre_list("T1190, T1595.001") == ["T1190", "T1595.001"]


def test_coerce_mitre_list_from_none_returns_empty() -> None:
    assert coerce_mitre_list(None) == []


def test_coerce_mitre_list_strips_whitespace_and_empties() -> None:
    assert coerce_mitre_list(" T1190 , , T1595.001 ") == [
        "T1190",
        "T1595.001",
    ]
