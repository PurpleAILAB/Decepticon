"""Adapter — read engagement-scoped KG data from the new KGStore and
build an in-memory :class:`KnowledgeGraph` for the reporting renderers.

The renderers in ``reporting/{hackerone,bugcrowd,executive,sarif,timeline}.py``
all operate on the :class:`KnowledgeGraph` Pydantic model. Rather than
rewriting every renderer in the same PR, this adapter reads from the
new :class:`KGStore` (the post-#545 backend) and constructs the same
``KnowledgeGraph`` shape — preserving deterministic Node / Edge IDs so
downstream consumers and existing test patches remain stable.

This module is the seam that lets ``tools/reporting`` retire the old
``tools/research/_state._load`` shim without touching the renderer
code or the back-end Neo4j wiring used by the (still legacy) AD /
Contract tool surfaces — those migrate in dedicated follow-up PRs.
"""

from __future__ import annotations

from typing import Any

from decepticon.middleware.kg_internal.store import (
    KGStore,
    KGStoreConfigError,
    KGStoreUnavailableError,
)
from decepticon_core.types.kg import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
)

# Provenance / reserved property names that ``KGStore`` auto-injects on
# every observation. They live on the Neo4j node so we can read them
# back when rebuilding the in-memory graph, but they don't belong on
# ``Node.props`` / ``Edge.props`` — those carry the agent-supplied
# props only. Strip them before constructing the Pydantic model.
#
# ``_legacy_id`` is the SHA1 the in-memory ``Node`` carried before
# persistence. The legacy ``_state`` shim stores it so edges (whose
# ``src`` / ``dst`` are SHA1s) can resolve their endpoints on round-trip.
# We strip it from ``Node.props`` on load and instead restore it onto
# ``Node.id`` directly, preserving the legacy graph's identity model.
_RESERVED_NODE_PROPS = frozenset(
    {
        "engagement",
        "key",
        "label",
        "firstseen",
        "lastupdated",
        "created_by",
        "source_episode_id",
        "_legacy_id",
    }
)
_RESERVED_EDGE_PROPS = frozenset(
    {
        "engagement",
        "key",
        "firstseen",
        "lastupdated",
        "created_by",
        "source_episode_id",
        "weight",
    }
)


def _coerce_props(raw: Any, reserved: frozenset[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k not in reserved}


def load_engagement_graph(engagement: str) -> KnowledgeGraph:
    """Build a :class:`KnowledgeGraph` from the new KGStore for one engagement.

    Returns an empty graph if the store is unavailable or unreachable —
    matches the soft-fail behaviour of the legacy ``_state._load`` so
    the reporting tools degrade gracefully when Neo4j is not running.
    """
    try:
        store = KGStore.from_env()
    except (KGStoreConfigError, KGStoreUnavailableError, ImportError):
        return KnowledgeGraph()

    graph = KnowledgeGraph()
    try:
        node_rows = store.execute_read(
            (
                "MATCH (n) WHERE n.engagement = $engagement "
                "RETURN labels(n)[0] AS kind, "
                "       n.key AS key, "
                "       n.label AS label, "
                "       properties(n) AS props, "
                "       coalesce(n.firstseen, 0.0) AS created_at, "
                "       coalesce(n.lastupdated, 0.0) AS updated_at"
            ),
            {"engagement": engagement},
            engagement=engagement,
        )
        for row in node_rows or []:
            kind_raw = row.get("kind")
            if not isinstance(kind_raw, str):
                continue
            try:
                kind = NodeKind(kind_raw)
            except ValueError:
                continue
            key = row.get("key") or ""
            label = row.get("label") or key or kind_raw
            raw_props = row.get("props") or {}
            props = _coerce_props(raw_props, _RESERVED_NODE_PROPS)
            node = Node.make(kind, str(label), key=str(key), **props)
            # Restore the legacy SHA1 id when the node was persisted
            # by the legacy shim — keeps edge.src / edge.dst lookups
            # consistent across round-trip.
            legacy_id = raw_props.get("_legacy_id") if isinstance(raw_props, dict) else None
            if isinstance(legacy_id, str) and legacy_id:
                node.id = legacy_id
            node.created_at = float(row.get("created_at") or 0.0)
            node.updated_at = float(row.get("updated_at") or 0.0)
            graph.nodes[node.id] = node

        edge_rows = store.execute_read(
            (
                "MATCH (a)-[r]->(b) "
                "WHERE a.engagement = $engagement AND r.engagement = $engagement "
                "  AND b.engagement = $engagement "
                "RETURN labels(a)[0] AS src_kind, "
                "       a.key AS src_key, "
                "       labels(b)[0] AS dst_kind, "
                "       b.key AS dst_key, "
                "       type(r) AS kind, "
                "       coalesce(r.weight, 1.0) AS weight, "
                "       properties(r) AS props, "
                "       coalesce(r.firstseen, 0.0) AS created_at"
            ),
            {"engagement": engagement},
            engagement=engagement,
        )
        for row in edge_rows or []:
            kind_raw = row.get("kind")
            src_kind_raw = row.get("src_kind")
            dst_kind_raw = row.get("dst_kind")
            src_key = row.get("src_key")
            dst_key = row.get("dst_key")
            if not (
                isinstance(kind_raw, str)
                and isinstance(src_kind_raw, str)
                and isinstance(dst_kind_raw, str)
                and isinstance(src_key, str)
                and isinstance(dst_key, str)
            ):
                continue
            try:
                kind = EdgeKind(kind_raw)
                src_kind = NodeKind(src_kind_raw)
                dst_kind = NodeKind(dst_kind_raw)
            except ValueError:
                continue
            src_id = Node.make(src_kind, src_key, key=src_key).id
            dst_id = Node.make(dst_kind, dst_key, key=dst_key).id
            weight = float(row.get("weight") or 1.0)
            props = _coerce_props(row.get("props"), _RESERVED_EDGE_PROPS)
            edge = Edge.make(src_id, dst_id, kind, weight=weight, **props)
            edge.created_at = float(row.get("created_at") or 0.0)
            graph.edges[edge.id] = edge

        return graph
    finally:
        store.close()
