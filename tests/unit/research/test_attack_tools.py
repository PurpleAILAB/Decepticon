"""Unit tests for the ATT&CK spine @tool wrappers."""

from __future__ import annotations

import json

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research import tools as research_tools
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.attack.tools import (
    ATTACK_TOOLS,
    kg_backfill_mitre,
    kg_link_finding_technique,
    mitre_lookup,
    mitre_skills_for_technique,
)
from decepticon.tools.research.graph import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind


class _FakeStore:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def load_graph(self):
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes):
        for n in nodes:
            self.graph.upsert_node(n)
        return len(nodes)

    def batch_upsert_edges(self, edges):
        for e in edges:
            self.graph.upsert_edge(e)
        return len(edges)

    def stats(self):
        return self.graph.stats()


class TestMitreLookup:
    def test_known_technique(self) -> None:
        payload = json.loads(mitre_lookup.invoke({"technique_id": "t1190"}))
        assert payload["id"] == "T1190"
        assert payload["name"]
        assert "initial-access" in payload["tactics"]

    def test_invalid_id(self) -> None:
        payload = json.loads(mitre_lookup.invoke({"technique_id": "not-an-id"}))
        assert "error" in payload

    def test_unknown_technique(self) -> None:
        payload = json.loads(mitre_lookup.invoke({"technique_id": "T9999"}))
        assert "error" in payload


class TestMitreSkillsForTechnique:
    def test_lists_skills_that_teach_technique(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        tech = fake.graph.upsert_node(
            Node.make(NodeKind.TECHNIQUE, "Exploit Public-Facing Application", key="T1190")
        )
        skill = fake.graph.upsert_node(
            Node.make(NodeKind.SKILL, "web-exploit", key="/skills/web/SKILL.md")
        )
        fake.graph.upsert_edge(Edge.make(skill.id, tech.id, EdgeKind.TEACHES))

        payload = json.loads(mitre_skills_for_technique.invoke({"technique_id": "T1190"}))
        assert payload["count"] == 1
        assert payload["skills"][0]["path"] == "/skills/web/SKILL.md"

    def test_no_skills_for_technique(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        payload = json.loads(mitre_skills_for_technique.invoke({"technique_id": "T1190"}))
        assert payload["count"] == 0


class TestKgBackfillMitre:
    def test_backfills_existing_findings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        fake.graph.upsert_node(Node.make(NodeKind.FINDING, "SQLi", key="FIND-1", mitre=["T1190"]))
        payload = json.loads(kg_backfill_mitre.invoke({}))
        assert payload["edges_linked"] == 1
        maps_to = [e for e in fake.graph.edges.values() if e.kind == EdgeKind.MAPS_TO]
        assert len(maps_to) == 1


class TestKgLinkFindingTechnique:
    def test_links_existing_node(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        finding = fake.graph.upsert_node(Node.make(NodeKind.FINDING, "RCE", key="FIND-1"))
        payload = json.loads(
            kg_link_finding_technique.invoke({"finding_id": finding.id, "technique_id": "T1190"})
        )
        assert payload["linked"] == 1
        maps_to = [e for e in fake.graph.edges.values() if e.kind == EdgeKind.MAPS_TO]
        assert maps_to[0].dst == technique_node_id("T1190")

    def test_missing_node_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        payload = json.loads(
            kg_link_finding_technique.invoke({"finding_id": "nonexistent", "technique_id": "T1190"})
        )
        assert "error" in payload


def test_attack_tools_registered_in_research_tools() -> None:
    assert ATTACK_TOOLS, "ATTACK_TOOLS must not be empty"
    for tool_obj in ATTACK_TOOLS:
        assert tool_obj in research_tools.RESEARCH_TOOLS
