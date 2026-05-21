"""Unit tests for finding deduplication (decepticon.tools.research.dedup)."""

from __future__ import annotations

import json

from decepticon.tools.research.dedup import (
    apply_dedup,
    cluster_findings,
    diff_signature,
    finding_signature,
    kg_dedup_findings,
    select_canonical,
)
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
)


class _FakeStore:
    def __init__(self):
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

    def ensure_schema(self):
        pass

    def close(self):
        pass

    def revision(self):
        return 0.0

    def stats(self):
        return self.graph.stats()

    def upsert_node(self, node):
        self.graph.upsert_node(node)

    def upsert_edge(self, edge):
        self.graph.upsert_edge(edge)


def _configure_kg(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr("decepticon.tools.research._state._store", fake)
    return fake


def _vuln(graph, key, *, cwe="CWE-89", file="/workspace/app.py", line=42, **extra):
    vuln = Node.make(
        NodeKind.VULNERABILITY, f"vuln {key}", key=key, cwe=[cwe], file=file, line=line, **extra
    )
    return graph.upsert_node(vuln)


def _finding(graph, key, vuln, *, validated=True, cvss_score=7.5, summary="poc"):
    finding = Node.make(
        NodeKind.FINDING,
        f"validated: {vuln.label}" if validated else f"rejected: {vuln.label}",
        key=key,
        validated=validated,
        vuln_id=vuln.id,
        cvss_score=cvss_score,
        summary=summary,
    )
    graph.upsert_node(finding)
    graph.upsert_edge(Edge.make(finding.id, vuln.id, EdgeKind.VALIDATES))
    return finding


class TestSignature:
    def test_reads_cwe_and_buckets_line(self):
        g = KnowledgeGraph()
        v = _vuln(g, "v1", cwe="CWE-89", file="/workspace/app.py", line=42)
        f = _finding(g, "finding::h1", v)
        sig = finding_signature(g, f)
        assert sig == ("CWE-89", "injection", "app.py:8")  # 42 // 5 == 8

    def test_falls_back_when_vuln_missing(self):
        g = KnowledgeGraph()
        orphan = Node.make(
            NodeKind.FINDING, "validated: orphan", key="finding::x", validated=True, vuln_id="gone"
        )
        g.upsert_node(orphan)
        sig = finding_signature(g, orphan)
        assert sig[2].startswith("finding:")


class TestClustering:
    def test_two_findings_same_signature_one_cluster(self):
        g = KnowledgeGraph()
        # Two distinct vulns, same CWE + file + line → same signature.
        v1 = _vuln(g, "v1", file="/workspace/app.py", line=40)
        v2 = _vuln(g, "v2", file="/workspace/app.py", line=42)  # 40//5 == 42//5 == 8
        _finding(g, "finding::a", v1)
        _finding(g, "finding::b", v2)
        clusters = cluster_findings(g)
        assert len(clusters) == 1
        assert len(next(iter(clusters.values()))) == 2

    def test_distinct_signatures_separate_clusters(self):
        g = KnowledgeGraph()
        v1 = _vuln(g, "v1", file="/workspace/app.py", line=40)
        v2 = _vuln(g, "v2", file="/workspace/other.py", line=40)
        _finding(g, "finding::a", v1)
        _finding(g, "finding::b", v2)
        assert len(cluster_findings(g)) == 2

    def test_rejected_findings_excluded(self):
        g = KnowledgeGraph()
        v = _vuln(g, "v1")
        _finding(g, "finding::a", v, validated=False)
        assert cluster_findings(g) == {}


class TestCanonical:
    def test_prefers_highest_cvss(self):
        g = KnowledgeGraph()
        v = _vuln(g, "v1")
        low = _finding(g, "finding::low", v, cvss_score=4.0)
        high = _finding(g, "finding::high", v, cvss_score=9.1)
        assert select_canonical([low, high]).id == high.id

    def test_tiebreak_prefers_oldest(self):
        g = KnowledgeGraph()
        v = _vuln(g, "v1")
        a = _finding(g, "finding::a", v, cvss_score=7.0, summary="same")
        b = _finding(g, "finding::b", v, cvss_score=7.0, summary="same")
        a.created_at = 100.0
        b.created_at = 200.0
        assert select_canonical([a, b]).id == a.id


class TestApplyDedup:
    def test_marks_duplicates_and_edge(self, monkeypatch):
        g = KnowledgeGraph()
        v1 = _vuln(g, "v1", file="/workspace/app.py", line=40)
        v2 = _vuln(g, "v2", file="/workspace/app.py", line=42)
        canon = _finding(g, "finding::canon", v1, cvss_score=9.0)
        dup = _finding(g, "finding::dup", v2, cvss_score=5.0)

        report = apply_dedup(g)
        assert report["duplicates_marked"] == 1
        assert report["clusters_with_duplicates"] == 1

        assert dup.props["duplicate_of"] == canon.id
        assert dup.props["superseded"] is True
        assert canon.props.get("canonical") is True
        edges = [e for e in g.edges.values() if e.kind == EdgeKind.DUPLICATE_OF]
        assert len(edges) == 1 and edges[0].src == dup.id and edges[0].dst == canon.id

    def test_idempotent(self):
        g = KnowledgeGraph()
        v1 = _vuln(g, "v1", line=40)
        v2 = _vuln(g, "v2", line=42)
        _finding(g, "finding::a", v1, cvss_score=9.0)
        _finding(g, "finding::b", v2, cvss_score=5.0)
        first = apply_dedup(g)
        nodes_before, edges_before = len(g.nodes), len(g.edges)
        second = apply_dedup(g)
        assert first == second
        assert (len(g.nodes), len(g.edges)) == (nodes_before, edges_before)

    def test_noop_on_single_finding(self):
        g = KnowledgeGraph()
        v = _vuln(g, "v1")
        _finding(g, "finding::solo", v)
        report = apply_dedup(g)
        assert report["duplicates_marked"] == 0
        assert report["clusters_with_duplicates"] == 0


class TestDiffSignature:
    def test_parses_hunks(self):
        patch = Node.make(
            NodeKind.PATCH,
            "patch",
            key="patch::1",
            diff="--- a/app.py\n+++ b/app.py\n@@ -10,5 +10,6 @@\n context\n",
        )
        assert diff_signature(patch) == {("app.py", 10, 16)}

    def test_patch_tier_merges_overlapping_diffs(self):
        g = KnowledgeGraph()
        # Two distinct signatures (different files) → 2 Tier-A clusters ...
        v1 = _vuln(g, "v1", file="/workspace/a.py", line=10)
        v2 = _vuln(g, "v2", file="/workspace/b.py", line=99)
        _finding(g, "finding::a", v1)
        _finding(g, "finding::b", v2)
        # ... but both patches share a diff_hash → Tier B merges them.
        g.upsert_node(
            Node.make(NodeKind.PATCH, "p1", key="patch::1", vuln_id=v1.id, diff_hash="shared")
        )
        g.upsert_node(
            Node.make(NodeKind.PATCH, "p2", key="patch::2", vuln_id=v2.id, diff_hash="shared")
        )
        assert len(cluster_findings(g)) == 2
        report = apply_dedup(g, use_patch_tier=True)
        assert report["duplicates_marked"] == 1


class TestKgDedupFindingsTool:
    def test_tool_returns_report(self, monkeypatch):
        fake = _configure_kg(monkeypatch)
        v1 = _vuln(fake.graph, "v1", line=40)
        v2 = _vuln(fake.graph, "v2", line=42)
        _finding(fake.graph, "finding::a", v1, cvss_score=9.0)
        _finding(fake.graph, "finding::b", v2, cvss_score=5.0)

        raw = kg_dedup_findings.invoke({})
        report = json.loads(raw)
        assert report["duplicates_marked"] == 1
        assert report["total_findings"] == 2

        graph = fake.load_graph()
        assert [e for e in graph.edges.values() if e.kind == EdgeKind.DUPLICATE_OF]
