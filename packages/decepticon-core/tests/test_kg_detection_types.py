"""Regression tests for the Blue Cell defensive KG vocabulary.

The Offensive Vaccine / Blue Cell loop (``docs/features/blue-cell.md``)
records *proven* detection coverage in the engagement knowledge graph:
each fired detection becomes a ``DetectionFired`` node linked
``-[:DETECTED]->`` the offensive ``Finding`` it caught and
``-[:USES_RULE]->`` the ``DefenseAction`` (Sigma/YARA artifact) that
produced it.

``NodeKind`` values are Neo4j labels and ``EdgeKind`` values are Neo4j
relationship types (1:1, per the ``kg`` module docstring), so the exact
strings below are a persistence wire contract the Blue Cell agent, the
Neo4j store, and the Defense Brief generator all build Cypher against.
Pin them here so a rename can't silently break the downstream loop.
"""

from __future__ import annotations

from decepticon_core.types.kg import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind


def test_detection_node_kinds_have_neo4j_labels() -> None:
    assert NodeKind.DETECTION_FIRED == "DetectionFired"
    assert NodeKind.DEFENSE_ACTION == "DefenseAction"


def test_detection_edge_kinds_have_neo4j_relationship_types() -> None:
    assert EdgeKind.DETECTED == "DETECTED"
    assert EdgeKind.USES_RULE == "USES_RULE"


def test_graph_records_detection_coverage_topology() -> None:
    """DetectionFired -[:DETECTED]-> Finding and -[:USES_RULE]-> DefenseAction."""
    graph = KnowledgeGraph()
    finding = graph.upsert_node(Node.make(NodeKind.FINDING, "Kerberoast on DC01", key="FIND-001"))
    rule = graph.upsert_node(
        Node.make(NodeKind.DEFENSE_ACTION, "DCEP-T1558.003-kerberoast", key="rule::DCEP-T1558.003")
    )
    fired = graph.upsert_node(
        Node.make(
            NodeKind.DETECTION_FIRED,
            "Kerberoast detection",
            key="detection::DCEP-T1558.003::1700000000.0",
            mttd_seconds=1.2,
        )
    )
    graph.upsert_edge(Edge.make(fired.id, finding.id, EdgeKind.DETECTED))
    graph.upsert_edge(Edge.make(fired.id, rule.id, EdgeKind.USES_RULE))

    detected = graph.neighbors(fired.id, edge_kind=EdgeKind.DETECTED)
    assert [n.id for _, n in detected] == [finding.id]

    uses_rule = graph.neighbors(fired.id, edge_kind=EdgeKind.USES_RULE)
    assert [n.id for _, n in uses_rule] == [rule.id]


def test_detection_gap_query_finds_undetected_findings() -> None:
    """A Finding with no inbound DETECTED edge is a detection gap.

    Surfacing these blind spots is the headline Blue Cell deliverable, so
    the vocabulary must make the query expressible.
    """
    graph = KnowledgeGraph()
    caught = graph.upsert_node(Node.make(NodeKind.FINDING, "DCSync", key="FIND-001"))
    graph.upsert_node(Node.make(NodeKind.FINDING, "DLL side-load", key="FIND-002"))
    fired = graph.upsert_node(
        Node.make(NodeKind.DETECTION_FIRED, "DCSync detection", key="detection::x::1.0")
    )
    graph.upsert_edge(Edge.make(fired.id, caught.id, EdgeKind.DETECTED))

    gaps = [
        node.label
        for node in graph.by_kind(NodeKind.FINDING)
        if not graph.neighbors(node.id, edge_kind=EdgeKind.DETECTED, direction="in")
    ]
    assert gaps == ["DLL side-load"]
