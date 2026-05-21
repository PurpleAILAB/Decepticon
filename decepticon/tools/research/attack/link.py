"""Resolve inert ATT&CK ``mitre`` props into graph edges.

Findings, vulnerabilities, and attack paths carry MITRE technique IDs as
plain ``mitre`` props. ``link_mitre`` turns those into ``MAPS_TO`` edges to
the pre-seeded ``Technique`` nodes — the join that makes ATT&CK queryable.
"""

from __future__ import annotations

from decepticon.tools.research.attack.catalog import is_technique_id, parse_ids
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.graph import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind

# Node kinds whose ``mitre`` prop the backfill resolves into MAPS_TO edges.
_LINKABLE_KINDS = (NodeKind.FINDING, NodeKind.VULNERABILITY, NodeKind.ATTACK_PATH)


def link_mitre(graph: KnowledgeGraph, src_node: Node, mitre_value: object) -> int:
    """Add ``MAPS_TO`` edges from ``src_node`` to ATT&CK ``Technique`` nodes.

    ``mitre_value`` is the raw ``mitre`` prop — a list or comma string.
    Tactic-level and invalid IDs are skipped (MAPS_TO targets techniques).
    Returns the count of technique links created or refreshed. The edge
    materializes in Neo4j only if the Technique node exists; it does, after
    reference-data seeding.
    """
    count = 0
    for tid in parse_ids(mitre_value):
        if not is_technique_id(tid):
            continue
        graph.upsert_edge(Edge.make(src_node.id, technique_node_id(tid), EdgeKind.MAPS_TO))
        count += 1
    return count


def backfill_mitre(graph: KnowledgeGraph) -> dict[str, int]:
    """Scan Finding/Vulnerability/AttackPath nodes and create any missing
    ``MAPS_TO`` edges from their ``mitre`` props. Idempotent."""
    scanned = 0
    linked = 0
    for kind in _LINKABLE_KINDS:
        for node in graph.by_kind(kind):
            mitre = node.props.get("mitre")
            if not mitre:
                continue
            scanned += 1
            linked += link_mitre(graph, node, mitre)
    return {"nodes_scanned": scanned, "edges_linked": linked}


__all__ = ["backfill_mitre", "link_mitre"]
