from __future__ import annotations

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, _kg_backend_name, _load, _save
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Severity,
)
from decepticon.tools.research.health import backend_health
from decepticon.tools.research.kgtools._helpers import _parse_props

# ── Knowledge graph tools ───────────────────────────────────────────────


@tool
def kg_add_node(kind: str, label: str, props: str = "{}") -> str:
    """Insert or update a node in the engagement knowledge graph.

    WHEN TO USE: Every time you observe an asset, vulnerability, credential,
    entrypoint, crown jewel, or code location. The graph persists across
    Ralph iterations, so a node you add now is queryable by the next
    fresh-context agent.

    NODE KINDS: host, service, url, repo, file, code_location, vulnerability,
    cve, finding, credential, secret, user, entrypoint, crown_jewel, chain,
    hypothesis.

    IMPORTANT: Use ``props`` to store severity, file path, port, cwe, cvss,
    etc. Supply a deterministic ``key`` inside props for deduplication
    (e.g. ``"key": "10.0.0.1:443/tcp"``).

    Args:
        kind: Node type (see NODE KINDS above).
        label: Human-readable label shown in graph summaries.
        props: JSON object with extra fields. Example:
            ``{"severity": "high", "cwe": ["CWE-89"], "file": "app.py", "line": 42}``

    Returns:
        JSON with the created/updated node id and stats.
    """
    try:
        node_kind = NodeKind(kind)
    except ValueError:
        return _json({"error": f"unknown kind: {kind}", "valid": [k.value for k in NodeKind]})
    parsed = _parse_props(props)
    graph, path = _load()
    node = graph.upsert_node(Node.make(node_kind, label, **parsed))
    _save(graph, path)
    return _json(
        {"id": node.id, "kind": node.kind.value, "label": node.label, "stats": graph.stats()}
    )


@tool
def kg_add_edge(src: str, dst: str, kind: str, weight: float = 1.0) -> str:
    """Connect two nodes with a typed, weighted edge.

    WHEN TO USE: After adding nodes, connect them to express relationships
    the chain planner can walk: ``runs_on``, ``has_vuln``, ``enables``,
    ``leaks``, ``grants``, ``chains_to``, etc.

    WEIGHT guides the chain planner — lower = easier to exploit. Defaults
    to 1.0. Use 0.3 for trivial wins, 2.0 for painful pivots.

    EDGE KINDS: runs_on, exposes, has_vuln, defined_in, located_at,
    affected_by, mapped_to, auth_as, grants, leaks, enables, chains_to,
    reaches, starts_at, contains, validates.

    Args:
        src: Source node id (from kg_add_node return value).
        dst: Destination node id.
        kind: Edge type.
        weight: Traversal cost (lower = easier exploitation).

    Returns:
        JSON with edge id and updated graph stats.
    """
    try:
        edge_kind = EdgeKind(kind)
    except ValueError:
        return _json({"error": f"unknown edge kind: {kind}", "valid": [k.value for k in EdgeKind]})
    graph, path = _load()
    if src not in graph.nodes or dst not in graph.nodes:
        return _json(
            {
                "error": "src or dst not in graph",
                "src_present": src in graph.nodes,
                "dst_present": dst in graph.nodes,
            }
        )
    edge = graph.upsert_edge(Edge.make(src, dst, edge_kind, weight=weight))
    _save(graph, path)
    return _json({"id": edge.id, "kind": edge.kind.value, "stats": graph.stats()})


@tool
def kg_query(kind: str = "", min_severity: str = "", limit: int = 25) -> str:
    """Query the knowledge graph for nodes matching kind / severity.

    WHEN TO USE: At the start of any iteration to discover what's already
    known. Before running a scanner, check if the target is already
    enumerated. Before exploiting, check for existing finding nodes.

    Args:
        kind: Node kind filter (empty = all kinds).
        min_severity: For vulnerability nodes only. Empty, low, medium,
            high, or critical. If set, only vulns meeting the bar are
            returned.
        limit: Max nodes to return (default 25).

    Returns:
        JSON list of matching nodes with their core fields and id.
    """
    graph, _ = _load()
    if min_severity:
        try:
            sev = Severity(min_severity.lower())
        except ValueError:
            return _json({"error": f"bad severity: {min_severity}"})
        nodes = graph.vulnerabilities_by_severity(sev)
    elif kind:
        try:
            node_kind = NodeKind(kind)
        except ValueError:
            return _json({"error": f"unknown kind: {kind}"})
        nodes = graph.by_kind(node_kind)
    else:
        nodes = list(graph.nodes.values())

    return _json(
        {
            "total": len(nodes),
            "returned": min(len(nodes), limit),
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind.value,
                    "label": n.label,
                    "props": n.props,
                }
                for n in nodes[:limit]
            ],
        }
    )


@tool
def kg_neighbors(node_id: str, direction: str = "out", edge_kind: str = "") -> str:
    """Walk one hop out from a node to see what it connects to.

    Args:
        node_id: Source node id.
        direction: "out" (default), "in", or "both".
        edge_kind: Optional edge-kind filter.

    Returns:
        JSON list of {edge, neighbor} pairs.
    """
    graph, _ = _load()
    if node_id not in graph.nodes:
        return _json({"error": "node not found", "id": node_id})
    filter_kind: EdgeKind | None = None
    if edge_kind:
        try:
            filter_kind = EdgeKind(edge_kind)
        except ValueError:
            return _json({"error": f"unknown edge kind: {edge_kind}"})
    neighbors = graph.neighbors(node_id, edge_kind=filter_kind, direction=direction)
    return _json(
        [
            {
                "edge_kind": e.kind.value,
                "edge_weight": e.weight,
                "neighbor_id": n.id,
                "neighbor_kind": n.kind.value,
                "neighbor_label": n.label,
            }
            for e, n in neighbors
        ]
    )


@tool
def kg_stats() -> str:
    """Return counts of nodes and edges by kind. Cheapest way to sanity check
    graph state at iteration start. Returns JSON stats dict."""
    graph, path = _load()
    return _json({"path": str(path), "backend": _kg_backend_name(), **graph.stats()})


@tool
def kg_backend_health() -> str:
    """Report KnowledgeGraph backend health/startup diagnostics.

    Use at session start (or when graph writes fail) to verify whether the
    configured backend is reachable and returning graph stats.
    """
    return _json(backend_health())
