"""Unit tests for technique-aware skill routing."""

from __future__ import annotations

import json

import pytest

from decepticon.tools.research.attack.catalog import (
    AttackCatalog,
    AttackTactic,
    AttackTechnique,
)
from decepticon.tools.research.attack.routing import route_skills, skills_for_objective
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.attack.skill_graph import build_skill_graph
from decepticon.tools.research.attack.skill_index import SkillRecord, skill_node_id
from decepticon.tools.research.graph import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind
from decepticon.tools.skills import recommend_skills


def _graph_with(skills: dict[str, list[str]]) -> KnowledgeGraph:
    """Build a graph: ``{skill_path: [technique_ids]}`` → Skill/Technique/TEACHES."""
    g = KnowledgeGraph()
    for path, techniques in skills.items():
        name = path.rstrip("/").split("/")[-1]
        g.upsert_node(Node.make(NodeKind.SKILL, name, key=path))
        for tid in techniques:
            g.upsert_node(Node.make(NodeKind.TECHNIQUE, tid, key=tid))
            g.upsert_edge(Edge.make(skill_node_id(path), technique_node_id(tid), EdgeKind.TEACHES))
    return g


class TestSkillsForObjective:
    def test_finds_skill_teaching_technique(self) -> None:
        g = _graph_with({"/skills/recon/SKILL.md": ["T1190"]})
        results = skills_for_objective(g, ["T1190"])
        assert len(results) == 1
        assert results[0]["path"] == "/skills/recon/SKILL.md"
        assert results[0]["match_count"] == 1

    def test_ranks_by_coverage(self) -> None:
        g = _graph_with(
            {
                "/skills/broad/SKILL.md": ["T1190", "T1059"],
                "/skills/narrow/SKILL.md": ["T1059"],
            }
        )
        results = skills_for_objective(g, ["T1190", "T1059"])
        assert results[0]["path"] == "/skills/broad/SKILL.md"
        assert results[0]["match_count"] == 2

    def test_subtechnique_falls_back_to_parent(self) -> None:
        # No skill teaches T1059.004 directly; one teaches the parent T1059.
        g = _graph_with({"/skills/exec/SKILL.md": ["T1059"]})
        results = skills_for_objective(g, ["T1059.004"])
        assert len(results) == 1
        assert results[0]["path"] == "/skills/exec/SKILL.md"

    def test_direct_subtechnique_hit_preferred_over_parent(self) -> None:
        g = _graph_with(
            {
                "/skills/specific/SKILL.md": ["T1059.004"],
                "/skills/generic/SKILL.md": ["T1059"],
            }
        )
        results = skills_for_objective(g, ["T1059.004"])
        # Direct hit on the sub-technique wins; the parent-only skill is not pulled in.
        assert len(results) == 1
        assert results[0]["path"] == "/skills/specific/SKILL.md"

    def test_empty_for_no_valid_techniques(self) -> None:
        g = _graph_with({"/skills/recon/SKILL.md": ["T1190"]})
        assert skills_for_objective(g, []) == []
        assert skills_for_objective(g, ["junk", "TA0001"]) == []

    def test_respects_max_results(self) -> None:
        g = _graph_with({f"/skills/s{i}/SKILL.md": ["T1190"] for i in range(10)})
        results = skills_for_objective(g, ["T1190"], max_results=3)
        assert len(results) == 3

    def test_accepts_comma_string(self) -> None:
        g = _graph_with({"/skills/recon/SKILL.md": ["T1190"]})
        results = skills_for_objective(g, "t1190")
        assert len(results) == 1


_CATALOG = AttackCatalog(
    version="test",
    tactics=[AttackTactic(id="TA0001", name="Initial Access", shortname="initial-access")],
    techniques=[
        AttackTechnique(id="T1190", name="Exploit Public-Facing Application"),
        AttackTechnique(id="T1059", name="Command and Scripting Interpreter"),
    ],
)


def _route(records: list[SkillRecord], mitre: object, **kwargs: object) -> list:
    return route_skills(build_skill_graph(records, _CATALOG), mitre, **kwargs)  # type: ignore[arg-type]


class TestRouteSkills:
    def test_returns_directly_teaching_skill(self) -> None:
        recs = [SkillRecord(name="web", path="/skills/web/SKILL.md", mitre=["T1190"])]
        routed = _route(recs, "T1190")
        assert len(routed) == 1
        assert routed[0].path == "/skills/web/SKILL.md"
        assert routed[0].reason == "direct"
        assert routed[0].slug == "web"

    def test_prerequisite_is_included_and_ordered_before_dependent(self) -> None:
        recs = [
            SkillRecord(
                name="web",
                path="/skills/web/SKILL.md",
                mitre=["T1190"],
                requires=["/skills/recon/SKILL.md"],
            ),
            SkillRecord(name="recon", path="/skills/recon/SKILL.md"),
        ]
        routed = _route(recs, "T1190")
        by_path = {r.path: r for r in routed}
        assert set(by_path) == {"/skills/web/SKILL.md", "/skills/recon/SKILL.md"}
        recon = by_path["/skills/recon/SKILL.md"]
        web = by_path["/skills/web/SKILL.md"]
        assert recon.reason == "prerequisite"
        assert recon.order < web.order
        # dependency-ordered: prerequisite comes first in the list
        assert routed[0].path == "/skills/recon/SKILL.md"

    def test_subtechnique_falls_back_to_parent(self) -> None:
        recs = [SkillRecord(name="exec", path="/skills/exec/SKILL.md", mitre=["T1059"])]
        routed = _route(recs, "T1059.004")
        assert len(routed) == 1
        assert routed[0].path == "/skills/exec/SKILL.md"

    def test_chain_expansion_adds_follow_on_skill(self) -> None:
        recs = [
            SkillRecord(
                name="web",
                path="/skills/web/SKILL.md",
                mitre=["T1190"],
                chains_to=["/skills/post/SKILL.md"],
            ),
            SkillRecord(name="post", path="/skills/post/SKILL.md"),
        ]
        routed = _route(recs, "T1190")
        by_path = {r.path: r for r in routed}
        assert by_path["/skills/post/SKILL.md"].reason == "chained"

    def test_chain_expansion_can_be_disabled(self) -> None:
        recs = [
            SkillRecord(
                name="web",
                path="/skills/web/SKILL.md",
                mitre=["T1190"],
                chains_to=["/skills/post/SKILL.md"],
            ),
            SkillRecord(name="post", path="/skills/post/SKILL.md"),
        ]
        routed = _route(recs, "T1190", expand_chains=False)
        assert {r.path for r in routed} == {"/skills/web/SKILL.md"}

    def test_refinement_demotes_the_general_skill(self) -> None:
        recs = [
            SkillRecord(
                name="sqli",
                path="/skills/sqli/SKILL.md",
                mitre=["T1190"],
                refines=["/skills/web/SKILL.md"],
            ),
            SkillRecord(name="web", path="/skills/web/SKILL.md", mitre=["T1190"]),
        ]
        routed = _route(recs, "T1190")
        by_path = {r.path: r for r in routed}
        assert by_path["/skills/sqli/SKILL.md"].reason == "direct"
        assert by_path["/skills/web/SKILL.md"].reason == "refines"
        # the specific skill outranks the one it refines
        assert by_path["/skills/sqli/SKILL.md"].score > by_path["/skills/web/SKILL.md"].score

    def test_observed_findings_boost_score(self) -> None:
        recs = [
            SkillRecord(name="a", path="/skills/a/SKILL.md", mitre=["T1190"]),
            SkillRecord(name="b", path="/skills/b/SKILL.md", mitre=["T1059"]),
        ]
        routed = _route(recs, "T1190, T1059", observed_findings="T1190")
        # both cover one technique, but a's technique was actually observed
        assert routed[0].path == "/skills/a/SKILL.md"

    def test_empty_for_no_valid_techniques(self) -> None:
        recs = [SkillRecord(name="web", path="/skills/web/SKILL.md", mitre=["T1190"])]
        assert _route(recs, []) == []
        assert _route(recs, ["TA0001", "junk"]) == []

    def test_respects_max_results(self) -> None:
        recs = [
            SkillRecord(name=f"s{i}", path=f"/skills/s{i}/SKILL.md", mitre=["T1190"])
            for i in range(10)
        ]
        routed = _route(recs, "T1190", max_results=3)
        assert len(routed) == 3


class TestRecommendSkillsTool:
    def test_returns_dependency_ordered_skills(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recs = [
            SkillRecord(
                name="web",
                path="/skills/web/SKILL.md",
                mitre=["T1190"],
                requires=["/skills/recon/SKILL.md"],
            ),
            SkillRecord(name="recon", path="/skills/recon/SKILL.md"),
        ]
        sg = build_skill_graph(recs, _CATALOG)
        monkeypatch.setattr("decepticon.tools.skills.get_skill_graph", lambda: sg)
        payload = json.loads(recommend_skills.invoke({"mitre_ids": "T1190"}))
        assert payload["count"] == 2
        # prerequisite is ordered first
        assert payload["skills"][0]["path"] == "/skills/recon/SKILL.md"
        assert payload["skills"][0]["reason"] == "prerequisite"

    def test_graceful_when_graph_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom():
            raise RuntimeError("skill graph build failed")

        monkeypatch.setattr("decepticon.tools.skills.get_skill_graph", _boom)
        payload = json.loads(recommend_skills.invoke({"mitre_ids": "T1190"}))
        assert payload["count"] == 0
        assert payload["skills"] == []
