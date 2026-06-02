"""Convert the YAML seeds (Phase, AssetType, MoC) into graph records.

Kept separate from ``seeds.py`` (which only parses YAML) so the loader
stays usable from validation tooling that does not need to construct
graph objects.
"""

from __future__ import annotations

from decepticon.skillogy.builder.model import Edge, Node
from decepticon.skillogy.builder.seeds import (
    load_asset_types,
    load_mocs,
    load_phases,
)


def emit_phase_records() -> tuple[list[Node], list[Edge]]:
    """Emit :Phase nodes (no edges — phases are leaves in this layer)."""
    nodes = [
        Node(
            label="Phase",
            key_field="name",
            properties={
                "name": p.name,
                "kill_chain_order": p.kill_chain_order,
                "kind": p.kind,
            },
        )
        for p in load_phases()
    ]
    return nodes, []


def emit_asset_type_records() -> tuple[list[Node], list[Edge]]:
    """Emit :AssetType nodes + HAS_SUBTYPE edges from each category to its child.

    The root category (``service``) has its category property set to
    ``root``; no HAS_SUBTYPE edge points to it.
    """
    seeds = load_asset_types()
    nodes = [
        Node(
            label="AssetType",
            key_field="name",
            properties={"name": at.name, "category": at.category},
        )
        for at in seeds
    ]
    edges: list[Edge] = []
    for at in seeds:
        if at.category == "root":
            continue
        edges.append(
            Edge(
                edge_type="HAS_SUBTYPE",
                from_label="AssetType",
                from_key_field="name",
                from_key=at.category,
                to_label="AssetType",
                to_key_field="name",
                to_key=at.name,
            )
        )
    return nodes, edges


def emit_moc_records() -> tuple[list[Node], list[Edge]]:
    """Emit :MoC nodes + a BELONGS_TO_PHASE edge per MoC.

    ``BELONGS_TO_PHASE`` is the MoC-side complement of the
    ``BELONGS_TO`` edge that :Skill nodes use to point at the same MoC.
    Keeping them as separate edge types makes the runtime traversal
    explicit (skills → MoCs → phases) without overloading a single
    edge name.
    """
    seeds = load_mocs()
    nodes = [
        Node(
            label="MoC",
            key_field="name",
            properties={
                "name": m.name,
                "parent_phase": m.parent_phase,
                "description": m.description,
            },
        )
        for m in seeds
    ]
    edges = [
        Edge(
            edge_type="BELONGS_TO_PHASE",
            from_label="MoC",
            from_key_field="name",
            from_key=m.name,
            to_label="Phase",
            to_key_field="name",
            to_key=m.parent_phase,
        )
        for m in seeds
    ]
    return nodes, edges


def emit_all_seed_records() -> tuple[list[Node], list[Edge]]:
    """Convenience: aggregate every seed module."""
    all_nodes: list[Node] = []
    all_edges: list[Edge] = []
    for fn in (emit_phase_records, emit_asset_type_records, emit_moc_records):
        nodes, edges = fn()
        all_nodes.extend(nodes)
        all_edges.extend(edges)
    return all_nodes, all_edges
