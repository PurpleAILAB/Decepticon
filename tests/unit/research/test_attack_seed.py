"""Unit tests for ATT&CK technique seeding into the knowledge graph."""

from __future__ import annotations

from decepticon.tools.research.attack.catalog import parse_catalog
from decepticon.tools.research.attack.seed import (
    seed_reference_data,
    seed_techniques,
    tactic_node_id,
    technique_graph_elements,
    technique_node_id,
)
from decepticon.tools.research.attack.skill_index import SkillRecord
from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph, NodeKind

_FIXTURE = {
    "version": "17.1",
    "tactics": [
        {"id": "TA0043", "name": "Reconnaissance", "shortname": "reconnaissance"},
        {"id": "TA0001", "name": "Initial Access", "shortname": "initial-access"},
    ],
    "techniques": [
        {"id": "T1190", "name": "Exploit Public-Facing Application", "tactics": ["initial-access"]},
        {"id": "T1595", "name": "Active Scanning", "tactics": ["reconnaissance"]},
        {
            "id": "T1595.001",
            "name": "Scanning IP Blocks",
            "tactics": ["reconnaissance"],
            "is_subtechnique": True,
            "parent": "T1595",
        },
    ],
}


class _GraphStore:
    """Test double matching the Neo4jStore batch-write interface."""

    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def batch_upsert_nodes(self, nodes: list) -> int:
        return self.graph.bulk_upsert_nodes(nodes)

    def batch_upsert_edges(self, edges: list) -> int:
        return self.graph.bulk_upsert_edges(edges)


class TestTechniqueGraphElements:
    def test_builds_a_node_per_technique_and_tactic(self) -> None:
        cat = parse_catalog(_FIXTURE)
        nodes, _edges = technique_graph_elements(cat)
        kinds = [n.kind for n in nodes]
        assert kinds.count(NodeKind.TECHNIQUE) == 3
        assert kinds.count(NodeKind.TACTIC) == 2

    def test_technique_node_carries_key_in_props(self) -> None:
        cat = parse_catalog(_FIXTURE)
        nodes, _edges = technique_graph_elements(cat)
        tech = next(
            n for n in nodes if n.kind == NodeKind.TECHNIQUE and n.label.startswith("Exploit")
        )
        assert tech.props["key"] == "T1190"

    def test_subtechnique_edge_to_parent(self) -> None:
        cat = parse_catalog(_FIXTURE)
        _nodes, edges = technique_graph_elements(cat)
        sub_edges = [e for e in edges if e.kind == EdgeKind.SUB_TECHNIQUE_OF]
        assert len(sub_edges) == 1
        assert sub_edges[0].src == technique_node_id("T1595.001")
        assert sub_edges[0].dst == technique_node_id("T1595")

    def test_technique_in_tactic_edge(self) -> None:
        cat = parse_catalog(_FIXTURE)
        _nodes, edges = technique_graph_elements(cat)
        in_tactic = [e for e in edges if e.kind == EdgeKind.IN_TACTIC]
        # 3 techniques each in exactly one tactic
        assert len(in_tactic) == 3
        t1190_edge = next(e for e in in_tactic if e.src == technique_node_id("T1190"))
        assert t1190_edge.dst == tactic_node_id("TA0001")

    def test_deterministic_ids_across_calls(self) -> None:
        cat = parse_catalog(_FIXTURE)
        nodes_a, _ = technique_graph_elements(cat)
        nodes_b, _ = technique_graph_elements(cat)
        assert {n.id for n in nodes_a} == {n.id for n in nodes_b}


class TestSeedTechniques:
    def test_seeds_nodes_and_edges_into_store(self) -> None:
        cat = parse_catalog(_FIXTURE)
        store = _GraphStore()
        counts = seed_techniques(store, catalog=cat)
        assert counts["techniques"] == 3
        assert counts["tactics"] == 2
        assert store.graph.stats()["node.Technique"] == 3
        assert store.graph.stats()["node.Tactic"] == 2

    def test_reseed_is_idempotent(self) -> None:
        cat = parse_catalog(_FIXTURE)
        store = _GraphStore()
        seed_techniques(store, catalog=cat)
        first = store.graph.stats()
        seed_techniques(store, catalog=cat)
        second = store.graph.stats()
        assert first == second


class TestSeedReferenceData:
    def test_seeds_both_techniques_and_skills(self) -> None:
        cat = parse_catalog(_FIXTURE)
        recs = [SkillRecord(name="recon", path="/skills/recon/SKILL.md", mitre=["T1190"])]
        store = _GraphStore()
        counts = seed_reference_data(store, catalog=cat, skill_records=recs)
        assert counts["techniques"] == 3
        assert counts["skills"] == 1
        stats = store.graph.stats()
        assert stats["node.Technique"] == 3
        assert stats["node.Skill"] == 1
        assert stats["edge.TEACHES"] == 1

    def test_reference_data_seed_is_idempotent(self) -> None:
        cat = parse_catalog(_FIXTURE)
        recs = [SkillRecord(name="recon", path="/skills/recon/SKILL.md", mitre=["T1190"])]
        store = _GraphStore()
        seed_reference_data(store, catalog=cat, skill_records=recs)
        first = store.graph.stats()
        seed_reference_data(store, catalog=cat, skill_records=recs)
        assert store.graph.stats() == first
