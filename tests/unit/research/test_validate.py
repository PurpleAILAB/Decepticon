"""Unit tests for skill-graph validation."""

from __future__ import annotations

from decepticon.tools.research.attack.catalog import (
    AttackCatalog,
    AttackTactic,
    AttackTechnique,
)
from decepticon.tools.research.attack.skill_index import SkillRecord
from decepticon.tools.research.attack.validate import validate_skill_graph

_CATALOG = AttackCatalog(
    version="test",
    tactics=[AttackTactic(id="TA0001", name="Initial Access", shortname="initial-access")],
    techniques=[
        AttackTechnique(id="T1190", name="Exploit Public-Facing Application"),
        AttackTechnique(id="T1059", name="Command and Scripting Interpreter"),
    ],
)


def _rec(
    name: str,
    *,
    requires: list[str] | None = None,
    chains_to: list[str] | None = None,
    refines: list[str] | None = None,
    mitre: list[str] | None = None,
) -> SkillRecord:
    return SkillRecord(
        name=name,
        path=f"/skills/{name}/SKILL.md",
        requires=requires or [],
        chains_to=chains_to or [],
        refines=refines or [],
        mitre=mitre or [],
    )


class TestValidateSkillGraph:
    def test_clean_graph_is_ok(self) -> None:
        recs = [_rec("a", requires=["/skills/b/SKILL.md"]), _rec("b")]
        diag = validate_skill_graph(recs, _CATALOG)
        assert diag.ok
        assert diag.errors == []
        assert diag.warnings == []

    def test_dangling_reference_is_error(self) -> None:
        recs = [_rec("a", requires=["/skills/missing/SKILL.md"])]
        diag = validate_skill_graph(recs, _CATALOG)
        assert not diag.ok
        assert any("missing" in e for e in diag.errors)

    def test_self_reference_is_error(self) -> None:
        recs = [_rec("a", refines=["/skills/a/SKILL.md"])]
        diag = validate_skill_graph(recs, _CATALOG)
        assert not diag.ok
        assert any("itself" in e for e in diag.errors)

    def test_requires_cycle_is_error(self) -> None:
        recs = [
            _rec("a", requires=["/skills/b/SKILL.md"]),
            _rec("b", requires=["/skills/a/SKILL.md"]),
        ]
        diag = validate_skill_graph(recs, _CATALOG)
        assert not diag.ok
        assert any("requires cycle" in e for e in diag.errors)

    def test_refines_cycle_is_error(self) -> None:
        recs = [
            _rec("a", refines=["/skills/b/SKILL.md"]),
            _rec("b", refines=["/skills/a/SKILL.md"]),
        ]
        diag = validate_skill_graph(recs, _CATALOG)
        assert not diag.ok
        assert any("refines cycle" in e for e in diag.errors)

    def test_chains_to_cycle_is_warning_not_error(self) -> None:
        recs = [
            _rec("a", chains_to=["/skills/b/SKILL.md"]),
            _rec("b", chains_to=["/skills/a/SKILL.md"]),
        ]
        diag = validate_skill_graph(recs, _CATALOG)
        assert diag.ok  # a warning does not break ok
        assert any("chains_to cycle" in w for w in diag.warnings)

    def test_unknown_attack_id_is_warning(self) -> None:
        recs = [_rec("a", mitre=["T9999"])]
        diag = validate_skill_graph(recs, _CATALOG)
        assert diag.ok
        assert any("T9999" in w for w in diag.warnings)

    def test_known_attack_id_produces_no_warning(self) -> None:
        recs = [_rec("a", mitre=["T1190"])]
        diag = validate_skill_graph(recs, _CATALOG)
        assert diag.warnings == []

    def test_counts_are_populated(self) -> None:
        recs = [_rec("a"), _rec("b")]
        diag = validate_skill_graph(recs, _CATALOG)
        assert diag.counts["skills"] == 2
