"""Unit tests for ATT&CK MAPS_TO backfill — resolving inert mitre props
into graph edges to Technique nodes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research import tools as research_tools
from decepticon.tools.research.attack.link import backfill_mitre, link_mitre
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph, Node, NodeKind


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


def _maps_to_edges(graph: KnowledgeGraph) -> list:
    return [e for e in graph.edges.values() if e.kind == EdgeKind.MAPS_TO]


class TestLinkMitre:
    def test_adds_maps_to_edges_to_technique_nodes(self) -> None:
        g = KnowledgeGraph()
        finding = g.upsert_node(Node.make(NodeKind.FINDING, "SQLi", key="FIND-001"))
        count = link_mitre(g, finding, ["T1190", "T1059"])
        assert count == 2
        dsts = {e.dst for e in _maps_to_edges(g)}
        assert dsts == {technique_node_id("T1190"), technique_node_id("T1059")}

    def test_handles_comma_string(self) -> None:
        g = KnowledgeGraph()
        finding = g.upsert_node(Node.make(NodeKind.FINDING, "x", key="FIND-002"))
        count = link_mitre(g, finding, "t1190, T1059")
        assert count == 2

    def test_skips_garbage_and_tactic_ids(self) -> None:
        g = KnowledgeGraph()
        finding = g.upsert_node(Node.make(NodeKind.FINDING, "x", key="FIND-003"))
        # TA0001 is a tactic, "junk" is invalid — neither yields a TEACHES target.
        count = link_mitre(g, finding, ["TA0001", "junk", "T1190"])
        assert count == 1

    def test_is_idempotent(self) -> None:
        g = KnowledgeGraph()
        finding = g.upsert_node(Node.make(NodeKind.FINDING, "x", key="FIND-004"))
        link_mitre(g, finding, ["T1190"])
        link_mitre(g, finding, ["T1190"])
        assert len(_maps_to_edges(g)) == 1


class TestBackfillMitre:
    def test_links_findings_vulns_and_paths(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.FINDING, "f", key="FIND-1", mitre=["T1190"]))
        g.upsert_node(Node.make(NodeKind.VULNERABILITY, "v", key="V-1", mitre=["T1059"]))
        g.upsert_node(Node.make(NodeKind.ATTACK_PATH, "p", key="PATH-1", mitre=["T1078"]))
        result = backfill_mitre(g)
        assert result["nodes_scanned"] == 3
        assert result["edges_linked"] == 3
        assert len(_maps_to_edges(g)) == 3

    def test_ignores_nodes_without_mitre_and_other_kinds(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.FINDING, "f", key="FIND-1"))  # no mitre
        g.upsert_node(Node.make(NodeKind.HOST, "h", key="H-1", mitre=["T1190"]))  # wrong kind
        result = backfill_mitre(g)
        assert result["nodes_scanned"] == 0
        assert result["edges_linked"] == 0

    def test_is_idempotent(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.FINDING, "f", key="FIND-1", mitre=["T1190"]))
        backfill_mitre(g)
        backfill_mitre(g)
        assert len(_maps_to_edges(g)) == 1


class TestKgAddNodeHook:
    def test_finding_with_mitre_gets_maps_to_edge(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        research_tools.kg_add_node.invoke(
            {
                "kind": "Finding",
                "label": "SQLi in login",
                "props": json.dumps({"key": "FIND-001", "mitre": ["T1190"]}),
            }
        )
        edges = _maps_to_edges(fake.graph)
        assert len(edges) == 1
        assert edges[0].dst == technique_node_id("T1190")

    def test_host_with_mitre_gets_no_maps_to_edge(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = _FakeStore()
        monkeypatch.setattr(state, "_store", fake)
        research_tools.kg_add_node.invoke(
            {
                "kind": "Host",
                "label": "10.0.0.1",
                "props": json.dumps({"key": "H-1", "mitre": ["T1190"]}),
            }
        )
        assert _maps_to_edges(fake.graph) == []
