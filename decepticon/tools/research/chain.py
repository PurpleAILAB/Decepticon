"""Attack-chain planner — Neo4j Cypher-native path search.

Given a Neo4j attack graph, compute multi-hop exploitation paths from
``Entrypoint`` nodes to ``CrownJewel`` nodes using APOC's weighted
shortest-path algorithms. The cost model combines:

- edge weight (analyst-assigned difficulty, lower = easier)
- vulnerability severity (critical shrinks cost, info grows it)
- node-level validation state (validated PoCs halve the cost)

All path computation runs inside Neo4j via Cypher — no Python-side
graph traversal. Results are returned as plain data structures that
callers can serialize or promote into ``AttackPath`` nodes via
:func:`promote_chain`.

Algorithm
---------
Uses ``apoc.algo.dijkstra`` for weighted shortest paths and
``apoc.path.expandConfig`` for reachability analysis. Cost is stored
on relationship ``cost`` properties, computed at ingestion time by
the ``_compute_edge_cost`` helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.tools.research._state import get_store
from decepticon.tools.research.graph import (
    SEVERITY_SCORE,
    EdgeKind,
    NodeKind,
    Severity,
)

log = get_logger("research.chain")

# Relationship types that represent attack progression (traversable for paths).
_ATTACK_REL_TYPES = "|".join(
    [
        EdgeKind.EXPLOITS.value,
        EdgeKind.ENABLES.value,
        EdgeKind.LEAKS.value,
        EdgeKind.LEADS_TO.value,
        EdgeKind.PIVOTS_TO.value,
        EdgeKind.ESCALATES_TO.value,
        EdgeKind.HAS_VULN.value,
        EdgeKind.CAN_ACCESS.value,
        EdgeKind.ADMIN_TO.value,
    ]
)

# Severity → multiplier. High severity shrinks cost (faster to reach).
_SEVERITY_MULTIPLIER: dict[str, float] = {
    Severity.CRITICAL.value: 0.4,
    Severity.HIGH.value: 0.6,
    Severity.MEDIUM.value: 1.0,
    Severity.LOW.value: 1.6,
    Severity.INFO.value: 2.5,
}


@dataclass(frozen=True)
class ChainStep:
    """One hop in an attack chain."""

    node_id: str
    node_label: str
    node_kind: str
    edge_kind: str
    hop_cost: float


@dataclass
class Chain:
    """A candidate attack chain from an entrypoint to a crown jewel."""

    entrypoint_id: str
    entrypoint_label: str
    crown_jewel_id: str
    crown_jewel_label: str
    steps: list[ChainStep] = field(default_factory=list)
    total_cost: float = 0.0

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def path_labels(self) -> list[str]:
        return [self.entrypoint_label] + [s.node_label for s in self.steps]

    def summary(self) -> str:
        arrow = " → ".join(self.path_labels)
        return f"cost={self.total_cost:.2f} len={self.length} {arrow}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entrypoint": self.entrypoint_label,
            "crown_jewel": self.crown_jewel_label,
            "total_cost": round(self.total_cost, 3),
            "length": self.length,
            "steps": [
                {
                    "node_id": s.node_id,
                    "node_label": s.node_label,
                    "node_kind": s.node_kind,
                    "edge_kind": s.edge_kind,
                    "hop_cost": round(s.hop_cost, 3),
                }
                for s in self.steps
            ],
        }


def compute_edge_cost(
    severity: str = "", validated: bool = False, base_weight: float = 1.0
) -> float:
    """Compute the traversal cost for an attack edge.

    This should be called at ingestion time and stored as the ``cost``
    property on relationships so Cypher path algorithms can use it.
    """
    mult = _SEVERITY_MULTIPLIER.get(severity, 1.0)
    if validated:
        mult *= 0.5
    return max(base_weight, 0.05) * mult


# ── Cypher-native path queries ─────────────────────────────────────────


def plan_chains(
    *,
    max_depth: int = 8,
    max_cost: float = 20.0,
    top_k: int = 10,
    entrypoint_ids: list[str] | None = None,
    crown_jewel_ids: list[str] | None = None,
) -> list[Chain]:
    """Enumerate and rank attack chains using Neo4j APOC dijkstra.

    Uses ``apoc.algo.dijkstra`` for weighted shortest path from each
    Entrypoint to each CrownJewel. Falls back to Cypher
    ``shortestPath`` if APOC is unavailable.

    Returns up to ``top_k`` chains, lowest total cost first.
    """
    store = get_store()

    # Build entry/goal filters
    if entrypoint_ids:
        entry_clause = "WHERE entry.id IN $entry_ids"
        params: dict[str, Any] = {"entry_ids": entrypoint_ids}
    else:
        entry_clause = ""
        params = {}

    if crown_jewel_ids:
        goal_clause = "WHERE crown.id IN $crown_ids"
        params["crown_ids"] = crown_jewel_ids
    else:
        goal_clause = ""

    params["max_cost"] = max_cost

    # Try APOC dijkstra first
    apoc_query = f"""
    MATCH (entry:Entrypoint) {entry_clause}
    MATCH (crown:CrownJewel) {goal_clause}
    CALL apoc.algo.dijkstra(entry, crown, '{_ATTACK_REL_TYPES}', 'cost')
    YIELD path, weight
    WHERE weight <= $max_cost AND length(path) <= {max_depth}
    RETURN entry.id AS entry_id,
           entry.label AS entry_label,
           crown.id AS crown_id,
           crown.label AS crown_label,
           weight AS total_cost,
           [n IN nodes(path) | {{id: n.id, label: n.label, kind: coalesce(n.kind, '')}}] AS path_nodes,
           [r IN relationships(path) | {{kind: type(r), cost: coalesce(r.cost, 1.0)}}] AS path_edges
    ORDER BY weight ASC
    LIMIT {top_k}
    """

    # Fallback: Cypher shortestPath (unweighted)
    fallback_query = f"""
    MATCH (entry:Entrypoint) {entry_clause}
    MATCH (crown:CrownJewel) {goal_clause}
    MATCH path = shortestPath((entry)-[:{_ATTACK_REL_TYPES}*..{max_depth}]->(crown))
    WITH entry, crown, path,
         reduce(c = 0.0, r IN relationships(path) | c + coalesce(r.cost, 1.0)) AS total_cost
    WHERE total_cost <= $max_cost
    RETURN entry.id AS entry_id,
           entry.label AS entry_label,
           crown.id AS crown_id,
           crown.label AS crown_label,
           total_cost,
           [n IN nodes(path) | {{id: n.id, label: n.label, kind: coalesce(n.kind, '')}}] AS path_nodes,
           [r IN relationships(path) | {{kind: type(r), cost: coalesce(r.cost, 1.0)}}] AS path_edges
    ORDER BY total_cost ASC
    LIMIT {top_k}
    """

    chains: list[Chain] = []

    try:
        rows = store.query_custom(apoc_query, params)
    except Exception:
        log.info("APOC dijkstra unavailable, falling back to shortestPath")
        try:
            rows = store.query_custom(fallback_query, params)
        except Exception as exc:
            log.warning("Chain planning failed", extra={"error": str(exc)})
            return []

    for row in rows:
        path_nodes = row.get("path_nodes", [])
        path_edges = row.get("path_edges", [])

        steps: list[ChainStep] = []
        # Skip first node (entrypoint) — steps are the intermediate + goal nodes
        for i, node_data in enumerate(path_nodes[1:]):
            edge_data = path_edges[i] if i < len(path_edges) else {}
            steps.append(
                ChainStep(
                    node_id=node_data.get("id", ""),
                    node_label=node_data.get("label", ""),
                    node_kind=node_data.get("kind", ""),
                    edge_kind=edge_data.get("kind", ""),
                    hop_cost=float(edge_data.get("cost", 1.0)),
                )
            )

        chains.append(
            Chain(
                entrypoint_id=row.get("entry_id", ""),
                entrypoint_label=row.get("entry_label", ""),
                crown_jewel_id=row.get("crown_id", ""),
                crown_jewel_label=row.get("crown_label", ""),
                steps=steps,
                total_cost=float(row.get("total_cost", 0.0)),
            )
        )

    return chains


def promote_chain(chain: Chain) -> str:
    """Materialize a computed chain as an AttackPath node in Neo4j.

    Creates the AttackPath node with STARTS_AT → entrypoint,
    REACHES → crown_jewel, and STEP → each intermediate node.
    Returns the AttackPath node id.
    """
    store = get_store()
    import hashlib

    path_key = f"chain::{chain.entrypoint_id}::{chain.crown_jewel_id}"
    node_id = hashlib.sha1(f"AttackPath::{path_key}".encode()).hexdigest()[:16]

    query = """
    MERGE (ap:AttackPath {id: $id})
    SET ap.key = $key,
        ap.label = $label,
        ap.kind = 'AttackPath',
        ap.total_cost = $total_cost,
        ap.length = $length,
        ap.validated = false,
        ap.created_at = coalesce(ap.created_at, $now),
        ap.updated_at = $now

    WITH ap

    MATCH (entry {id: $entry_id})
    MERGE (ap)-[:STARTS_AT]->(entry)

    WITH ap

    MATCH (crown {id: $crown_id})
    MERGE (ap)-[:REACHES]->(crown)
    """

    import time

    params = {
        "id": node_id,
        "key": path_key,
        "label": chain.summary(),
        "total_cost": round(chain.total_cost, 3),
        "length": chain.length,
        "entry_id": chain.entrypoint_id,
        "crown_id": chain.crown_jewel_id,
        "now": time.time(),
    }

    store.query_custom(query, params)

    # Add STEP relationships to intermediate nodes
    for i, step in enumerate(chain.steps):
        step_query = """
        MATCH (ap:AttackPath {id: $ap_id}), (n {id: $node_id})
        MERGE (ap)-[s:STEP {order: $order}]->(n)
        """
        store.query_custom(
            step_query,
            {
                "ap_id": node_id,
                "node_id": step.node_id,
                "order": i,
            },
        )

    return node_id


def critical_path_score(chain: Chain) -> float:
    """Single-number rating for a chain used by the orchestrator prioritiser.

    Combines inverse cost and severity-of-worst-hop so chains with one
    critical pivot aren't masked by a generally cheap path.
    """
    # Find worst severity among vulnerability nodes in the path
    worst_sev = 0.0
    store = get_store()

    vuln_ids = [s.node_id for s in chain.steps if s.node_kind == NodeKind.VULNERABILITY.value]
    if vuln_ids:
        query = """
        UNWIND $ids AS nid
        MATCH (v:Vulnerability {id: nid})
        RETURN coalesce(v.severity, 'info') AS severity
        """
        try:
            rows = store.query_custom(query, {"ids": vuln_ids})
            for row in rows:
                sev_str = row.get("severity", "info")
                try:
                    score = SEVERITY_SCORE.get(Severity(sev_str), 0.0)
                except ValueError:
                    score = 0.0
                if score > worst_sev:
                    worst_sev = score
        except Exception:
            pass  # APOC unavailable — fall back to shortestPath

    inv_cost = 1.0 / max(chain.total_cost, 0.1)
    return round(0.6 * inv_cost * 10 + 0.4 * worst_sev, 2)


def impact_analysis(node_id: str, max_depth: int = 4) -> list[dict[str, Any]]:
    """From a given node, what becomes reachable via attack relationships?

    Uses APOC path expansion to find all nodes reachable within max_depth
    hops through attack-progression relationships.
    """
    store = get_store()

    query = f"""
    MATCH (start {{id: $node_id}})
    CALL apoc.path.expandConfig(start, {{
      relationshipFilter: '{_ATTACK_REL_TYPES}',
      maxLevel: {max_depth},
      uniqueness: 'NODE_GLOBAL'
    }})
    YIELD path
    WITH last(nodes(path)) AS reachable, length(path) AS depth
    RETURN DISTINCT reachable.id AS id,
           labels(reachable)[0] AS type,
           reachable.label AS label,
           depth
    ORDER BY depth ASC
    """

    try:
        return store.query_custom(query, {"node_id": node_id})
    except Exception as exc:
        log.warning("Impact analysis failed", extra={"error": str(exc)})
        return []


def unexplored_surface() -> list[dict[str, Any]]:
    """Find hosts with services that have no vulnerability analysis yet."""
    store = get_store()

    query = """
    MATCH (h:Host)-[:HOSTS]->(s:Service)
    WHERE NOT (s)-[:HAS_VULN]->()
      AND h.explored = false
    RETURN h.id AS host_id,
           h.ip AS ip,
           h.hostname AS hostname,
           collect(s.port + '/' + coalesce(s.product, '')) AS services
    ORDER BY size(collect(s.port)) DESC
    """

    try:
        return store.query_custom(query, {})
    except Exception as exc:
        log.warning("Unexplored surface query failed", extra={"error": str(exc)})
        return []


def credential_reachability(credential_id: str) -> list[dict[str, Any]]:
    """From a credential, what hosts/services/users are reachable?"""
    store = get_store()

    query = """
    MATCH (cred:Credential {id: $cred_id})-[:AUTHENTICATES_TO]->(u:User)
    OPTIONAL MATCH (u)-[:CAN_ACCESS|ADMIN_TO]->(target)
    OPTIONAL MATCH (u)-[:HAS_SESSION]->(session_host:Host)
    RETURN cred.id AS cred_id,
           u.username AS identity,
           collect(DISTINCT {type: labels(target)[0], name: coalesce(target.ip, target.label, '')}) AS accessible_targets,
           collect(DISTINCT session_host.ip) AS active_sessions
    """

    try:
        return store.query_custom(query, {"cred_id": credential_id})
    except Exception as exc:
        log.warning("Credential reachability failed", extra={"error": str(exc)})
        return []
