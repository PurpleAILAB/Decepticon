"""Unit tests for technique-aware skill routing."""

from __future__ import annotations

import json

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research.attack.routing import skills_for_objective
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.attack.skill_index import skill_node_id
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


class _FakeStore:
    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def load_graph(self):
        return self.graph.model_copy(deep=True)


class TestRecommendSkillsTool:
    def test_returns_ranked_skills(self, monkeypatch: pytest.MonkeyPatch) -> None:
        graph = _graph_with({"/skills/recon/SKILL.md": ["T1190"]})
        monkeypatch.setattr(state, "_store", _FakeStore(graph))
        payload = json.loads(recommend_skills.invoke({"mitre_ids": "T1190"}))
        assert payload["count"] == 1
        assert payload["skills"][0]["path"] == "/skills/recon/SKILL.md"

    def test_graceful_when_graph_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom():
            raise RuntimeError("neo4j down")

        monkeypatch.setattr(state, "_load", _boom)
        payload = json.loads(recommend_skills.invoke({"mitre_ids": "T1190"}))
        assert payload["count"] == 0
        assert payload["skills"] == []
