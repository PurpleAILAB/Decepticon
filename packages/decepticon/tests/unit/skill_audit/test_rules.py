"""Tests for composed validation rules R-missing-required, R-bad-subdomain,
R-bad-mitre-format, R-no-attribution."""

from __future__ import annotations

from pathlib import Path

from decepticon.skill_audit.rules import (
    RuleId,
    Violation,
    validate_skill_file,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _path_inside_offensive_tree(name: str) -> str:
    # All offensive fixtures are reported under a recon path; reporting
    # fixture is reported under reporting path. The validator only reads
    # the supplied path string for kind inference.
    if "reporting" in name:
        return f"/skills/standard/reporting/{name}/SKILL.md"
    return f"/skills/standard/recon/{name}/SKILL.md"


def _ids(violations: list[Violation]) -> set[RuleId]:
    return {v.rule_id for v in violations}


def test_clean_fixture_produces_no_violations() -> None:
    text = (FIXTURES / "clean.md").read_text(encoding="utf-8")
    violations = validate_skill_file(_path_inside_offensive_tree("clean"), text)
    assert violations == []


def test_missing_subdomain_triggers_missing_required() -> None:
    text = (FIXTURES / "missing_subdomain.md").read_text(encoding="utf-8")
    violations = validate_skill_file(_path_inside_offensive_tree("missing-subdomain"), text)
    assert RuleId.MISSING_REQUIRED in _ids(violations)


def test_bad_mitre_triggers_bad_mitre_format() -> None:
    text = (FIXTURES / "bad_mitre.md").read_text(encoding="utf-8")
    violations = validate_skill_file(_path_inside_offensive_tree("bad-mitre"), text)
    assert RuleId.BAD_MITRE_FORMAT in _ids(violations)


def test_no_attribution_triggers_when_offensive() -> None:
    text = (FIXTURES / "no_attribution.md").read_text(encoding="utf-8")
    violations = validate_skill_file(_path_inside_offensive_tree("no-attribution"), text)
    assert RuleId.NO_ATTRIBUTION in _ids(violations)


def test_reporting_skill_is_exempt_from_attribution_rule() -> None:
    text = (FIXTURES / "reporting_skill.md").read_text(encoding="utf-8")
    violations = validate_skill_file(_path_inside_offensive_tree("reporting-example"), text)
    assert RuleId.NO_ATTRIBUTION not in _ids(violations)


def test_bad_subdomain_triggers_bad_subdomain_rule() -> None:
    text = (
        "---\n"
        "name: x\n"
        "description: x\n"
        "metadata:\n"
        "  subdomain: not-a-real-phase\n"
        "  when_to_use: x\n"
        "---\n"
        "body\n"
    )
    violations = validate_skill_file("/skills/standard/recon/x/SKILL.md", text)
    assert RuleId.BAD_SUBDOMAIN in _ids(violations)


def test_aliased_subdomain_is_accepted_as_canonical() -> None:
    text = (
        "---\n"
        "name: x\n"
        "description: x\n"
        "metadata:\n"
        "  subdomain: reverser\n"
        "  when_to_use: x\n"
        "  mitre_attack:\n"
        "    - T1190\n"
        "---\n"
        "body\n"
    )
    violations = validate_skill_file("/skills/standard/reverse-engineering/x/SKILL.md", text)
    assert RuleId.BAD_SUBDOMAIN not in _ids(violations)
