"""Unit tests for the KnowledgeGraph core."""

from __future__ import annotations

import pytest

from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)


class TestNodeDedup:
    def test_same_kind_and_label_yields_same_id(self) -> None:
        a = Node.make(NodeKind.HOST, "10.0.0.1")
        b = Node.make(NodeKind.HOST, "10.0.0.1")
        assert a.id == b.id

    def test_different_kind_yields_different_id(self) -> None:
        a = Node.make(NodeKind.HOST, "10.0.0.1")
        b = Node.make(NodeKind.SERVICE, "10.0.0.1")
        assert a.id != b.id

    def test_explicit_key_overrides_label_in_hash(self) -> None:
        a = Node.make(NodeKind.SERVICE, "http", key="10.0.0.1:80")
        b = Node.make(NodeKind.SERVICE, "DIFFERENT LABEL", key="10.0.0.1:80")
        # Same key → same ID despite different labels
        assert a.id == b.id

    def test_props_merge_on_upsert(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.HOST, "10.0.0.1", os="linux"))
        g.upsert_node(Node.make(NodeKind.HOST, "10.0.0.1", version="22.04"))
        host = g.by_kind(NodeKind.HOST)[0]
        assert host.props["os"] == "linux"
        assert host.props["version"] == "22.04"


class TestEdgeOperations:
    def test_edge_deterministic_id(self) -> None:
        e1 = Edge.make("a", "b", EdgeKind.HOSTS)
        e2 = Edge.make("a", "b", EdgeKind.HOSTS)
        assert e1.id == e2.id

    def test_upsert_edge_overrides_weight(self) -> None:
        g = KnowledgeGraph()
        a = g.upsert_node(Node.make(NodeKind.HOST, "a"))
        b = g.upsert_node(Node.make(NodeKind.HOST, "b"))
        g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.ENABLES, weight=2.0))
        g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.ENABLES, weight=0.5))
        edges = list(g.edges.values())
        assert len(edges) == 1
        assert edges[0].weight == 0.5


class TestQueries:
    def setup_method(self) -> None:
        self.g = KnowledgeGraph()
        self.h = self.g.upsert_node(Node.make(NodeKind.HOST, "10.0.0.1"))
        self.s80 = self.g.upsert_node(Node.make(NodeKind.SERVICE, "http:80", key="10.0.0.1:80"))
        self.s443 = self.g.upsert_node(Node.make(NodeKind.SERVICE, "https:443", key="10.0.0.1:443"))
        self.v_high = self.g.upsert_node(Node.make(NodeKind.VULNERABILITY, "SQLi", severity="high"))
        self.v_low = self.g.upsert_node(Node.make(NodeKind.VULNERABILITY, "XSS", severity="low"))
        self.v_crit = self.g.upsert_node(
            Node.make(NodeKind.VULNERABILITY, "RCE", severity="critical")
        )
        self.g.upsert_edge(Edge.make(self.s80.id, self.h.id, EdgeKind.HOSTS))
        self.g.upsert_edge(Edge.make(self.s80.id, self.v_high.id, EdgeKind.HAS_VULN, weight=0.5))

    def test_by_kind(self) -> None:
        services = self.g.by_kind(NodeKind.SERVICE)
        assert len(services) == 2
        assert {s.label for s in services} == {"http:80", "https:443"}

    def test_find_by_props(self) -> None:
        highs = self.g.find(kind=NodeKind.VULNERABILITY, severity="high")
        assert len(highs) == 1
        assert highs[0].label == "SQLi"

    def test_vulns_by_severity_ordering(self) -> None:
        vulns = self.g.vulnerabilities_by_severity(Severity.LOW)
        assert [v.label for v in vulns] == ["RCE", "SQLi", "XSS"]

    def test_vulns_by_severity_threshold(self) -> None:
        vulns = self.g.vulnerabilities_by_severity(Severity.HIGH)
        assert [v.label for v in vulns] == ["RCE", "SQLi"]

    def test_neighbors_out(self) -> None:
        pairs = self.g.neighbors(self.s80.id, direction="out")
        kinds = {e.kind.value for e, _ in pairs}
        assert kinds == {"HOSTS", "HAS_VULN"}

    def test_neighbors_in(self) -> None:
        pairs = self.g.neighbors(self.h.id, direction="in")
        assert len(pairs) == 1
        assert pairs[0][1].label == "http:80"

    def test_neighbors_edge_kind_filter(self) -> None:
        pairs = self.g.neighbors(self.s80.id, edge_kind=EdgeKind.HAS_VULN)
        assert len(pairs) == 1
        assert pairs[0][1].label == "SQLi"

    def test_neighbors_bad_direction_raises(self) -> None:
        with pytest.raises(ValueError):
            self.g.neighbors(self.h.id, direction="sideways")


class TestRemoval:
    def test_remove_node_drops_edges(self) -> None:
        g = KnowledgeGraph()
        a = g.upsert_node(Node.make(NodeKind.HOST, "a"))
        b = g.upsert_node(Node.make(NodeKind.HOST, "b"))
        c = g.upsert_node(Node.make(NodeKind.HOST, "c"))
        g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.ENABLES))
        g.upsert_edge(Edge.make(b.id, c.id, EdgeKind.ENABLES))
        g.upsert_edge(Edge.make(a.id, c.id, EdgeKind.ENABLES))
        removed = g.remove_node(b.id)
        assert removed == 3  # b + 2 edges touching it
        assert b.id not in g.nodes
        assert len(g.edges) == 1  # only a→c remains


class TestPathIteration:
    def test_iter_paths_finds_simple_path(self) -> None:
        g = KnowledgeGraph()
        a = g.upsert_node(Node.make(NodeKind.HOST, "a"))
        b = g.upsert_node(Node.make(NodeKind.HOST, "b"))
        c = g.upsert_node(Node.make(NodeKind.HOST, "c"))
        g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.ENABLES))
        g.upsert_edge(Edge.make(b.id, c.id, EdgeKind.ENABLES))
        paths = list(g.iter_paths(a.id, c.id))
        assert len(paths) == 1
        assert paths[0] == [a.id, b.id, c.id]

    def test_iter_paths_depth_limit(self) -> None:
        g = KnowledgeGraph()
        n = [g.upsert_node(Node.make(NodeKind.HOST, f"n{i}")) for i in range(6)]
        for i in range(5):
            g.upsert_edge(Edge.make(n[i].id, n[i + 1].id, EdgeKind.ENABLES))
        # max_depth=3 means path can have at most 3 nodes, not enough to reach n5
        paths = list(g.iter_paths(n[0].id, n[5].id, max_depth=3))
        assert paths == []

    def test_iter_paths_avoids_revisits(self) -> None:
        g = KnowledgeGraph()
        a = g.upsert_node(Node.make(NodeKind.HOST, "a"))
        b = g.upsert_node(Node.make(NodeKind.HOST, "b"))
        c = g.upsert_node(Node.make(NodeKind.HOST, "c"))
        g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.ENABLES))
        g.upsert_edge(Edge.make(b.id, a.id, EdgeKind.ENABLES))  # cycle
        g.upsert_edge(Edge.make(b.id, c.id, EdgeKind.ENABLES))
        paths = list(g.iter_paths(a.id, c.id))
        # No path should contain a twice
        for p in paths:
            assert len(set(p)) == len(p)


class TestStats:
    def test_stats_counts_kinds(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.HOST, "a"))
        g.upsert_node(Node.make(NodeKind.HOST, "b"))
        g.upsert_node(Node.make(NodeKind.VULNERABILITY, "v"))
        s = g.stats()
        assert s["nodes"] == 3
        assert s["node.Host"] == 2
        assert s["node.Vulnerability"] == 1
