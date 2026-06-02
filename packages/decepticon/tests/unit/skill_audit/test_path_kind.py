"""Tests for path-based offensive/non-offensive inference."""

from __future__ import annotations

import pytest

from decepticon.skill_audit.path_kind import is_offensive_path


@pytest.mark.parametrize(
    "path",
    [
        "/skills/standard/recon/web-recon/SKILL.md",
        "/skills/standard/exploit/web/sql-injection/SKILL.md",
        "/skills/standard/ad/kerberoasting/SKILL.md",
        "/skills/standard/ics/T0800-firmware-mode/SKILL.md",
        "/skills/standard/ai-security/prompt-injection/SKILL.md",
        "/skills/plugins/exploiter/some-skill/SKILL.md",
    ],
)
def test_offensive_paths_return_true(path: str) -> None:
    assert is_offensive_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/skills/standard/reporting/finding-write-up/SKILL.md",
        "/skills/standard/analyst/ml-model-extraction/SKILL.md",
        "/skills/plugins/scanner/reporting/some-skill/SKILL.md",
    ],
)
def test_non_offensive_paths_return_false(path: str) -> None:
    assert is_offensive_path(path) is False


def test_handles_relative_paths() -> None:
    # The validator works from absolute / repo-rooted paths but should
    # also handle relative ones without crashing.
    assert (
        is_offensive_path("packages/decepticon/decepticon/skills/standard/recon/x/SKILL.md") is True
    )
    assert (
        is_offensive_path("packages/decepticon/decepticon/skills/standard/reporting/x/SKILL.md")
        is False
    )
