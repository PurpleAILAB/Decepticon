"""Seed the ATT&CK technique/tactic layer into the knowledge graph.

``Technique`` and ``Tactic`` are global reference data — not engagement
scoped. Seeding is idempotent: node IDs are deterministic (SHA1 of kind +
ATT&CK ID), so re-seeding is a no-op MERGE.
"""

from __future__ import annotations

from decepticon.tools.research.attack.catalog import AttackCatalog, load_attack_catalog
from decepticon.tools.research.graph import Edge, EdgeKind, Node, NodeKind

# ── Deterministic node-ID helpers ────────────────────────────────────────
#
# A node's ID depends only on (kind, key) — the label is irrelevant — so
# these helpers let other modules (skill_index, link) reference technique
# and tactic nodes without a graph lookup.


def technique_node_id(technique_id: str) -> str:
    """Deterministic graph node ID for an ATT&CK technique."""
    return Node.make(NodeKind.TECHNIQUE, technique_id, key=technique_id).id


def tactic_node_id(tactic_id: str) -> str:
    """Deterministic graph node ID for an ATT&CK tactic."""
    return Node.make(NodeKind.TACTIC, tactic_id, key=tactic_id).id


# ── Graph element construction ───────────────────────────────────────────


def technique_graph_elements(catalog: AttackCatalog) -> tuple[list[Node], list[Edge]]:
    """Build (nodes, edges) for the full technique/tactic layer.

    Pure — does not touch any store. Produces one node per tactic and
    technique, a ``SUB_TECHNIQUE_OF`` edge for every sub-technique, and an
    ``IN_TACTIC`` edge for every (technique, tactic) membership.
    """
    nodes: list[Node] = []
    edges: list[Edge] = []

    for tac in catalog.tactics:
        nodes.append(
            Node.make(
                NodeKind.TACTIC,
                tac.name,
                key=tac.id,
                shortname=tac.shortname,
                description=tac.description,
            )
        )

    for tech in catalog.techniques:
        nodes.append(
            Node.make(
                NodeKind.TECHNIQUE,
                tech.name,
                key=tech.id,
                tactics=list(tech.tactics),
                description=tech.description,
                is_subtechnique=tech.is_subtechnique,
                parent=tech.parent,
                url=tech.url,
            )
        )
        if tech.parent:
            edges.append(
                Edge.make(
                    technique_node_id(tech.id),
                    technique_node_id(tech.parent),
                    EdgeKind.SUB_TECHNIQUE_OF,
                )
            )
        for shortname in tech.tactics:
            tac = catalog.tactic_by_shortname(shortname)
            if tac is not None:
                edges.append(
                    Edge.make(
                        technique_node_id(tech.id),
                        tactic_node_id(tac.id),
                        EdgeKind.IN_TACTIC,
                    )
                )

    return nodes, edges


def seed_techniques(store, catalog: AttackCatalog | None = None) -> dict[str, int]:
    """Seed the technique/tactic layer into ``store``.

    ``store`` is any object exposing ``batch_upsert_nodes`` and
    ``batch_upsert_edges`` (the :class:`Neo4jStore` write interface).
    Idempotent. Returns counts for logging.
    """
    catalog = catalog or load_attack_catalog()
    nodes, edges = technique_graph_elements(catalog)
    store.batch_upsert_nodes(nodes)
    store.batch_upsert_edges(edges)
    return {
        "techniques": len(catalog.techniques),
        "tactics": len(catalog.tactics),
        "edges": len(edges),
    }


def seed_reference_data(
    store,
    catalog: AttackCatalog | None = None,
    skill_records=None,
) -> dict[str, int]:
    """Seed the full global reference layer — techniques, tactics, skills.

    This is the single entry point called once at store initialization.
    Idempotent (deterministic node IDs). Returns merged counts. ``catalog``
    and ``skill_records`` default to the bundled datasets.
    """
    # Lazy import — skill_index imports technique_node_id from this module.
    from decepticon.tools.research.attack.skill_index import seed_skills

    tech_counts = seed_techniques(store, catalog=catalog)
    skill_counts = seed_skills(store, records=skill_records)
    return {**tech_counts, **skill_counts}


__all__ = [
    "seed_reference_data",
    "seed_techniques",
    "tactic_node_id",
    "technique_graph_elements",
    "technique_node_id",
]
