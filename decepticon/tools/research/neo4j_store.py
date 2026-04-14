"""Neo4j persistence backend for :mod:`decepticon.research.graph`.

The research stack still works with the default JSON file backend, but this
module enables migrating the knowledge graph to a real graph database for
multi-agent / multi-process workloads.

Activation is controlled by environment variables consumed by
``decepticon.research._state``:

- ``DECEPTICON_KG_BACKEND=neo4j``
- ``DECEPTICON_NEO4J_URI``
- ``DECEPTICON_NEO4J_USER``
- ``DECEPTICON_NEO4J_PASSWORD``
- ``DECEPTICON_NEO4J_DATABASE`` (optional, default: ``neo4j``)

Implementation note:
All writes go through MERGE-based upserts (individual nodes/edges or batches).
Each NodeKind maps to a native Neo4j label (e.g., Host, Service, Vulnerability)
and each EdgeKind maps to a native Neo4j relationship type (e.g., HOSTS, HAS_VULN).
This replaces the old replace-all strategy with incremental upserts.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.tools.research.graph import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind

log = get_logger("research.neo4j")


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j backend is requested but not usable."""


# ── NodeKind → Neo4j label ───────────────────────────────────────────────
# NodeKind values are already PascalCase and match Neo4j labels directly.
# No mapping dict needed — kind.value IS the label.

_ALL_NODE_LABELS: list[str] = [k.value for k in NodeKind]


def _label_for(kind: NodeKind) -> str:
    """Return the Neo4j label for a given NodeKind (identity — value is the label)."""
    return kind.value


@dataclass(slots=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> Neo4jConfig:
        uri = os.environ.get("DECEPTICON_NEO4J_URI", "").strip()
        user = os.environ.get("DECEPTICON_NEO4J_USER", "").strip()
        password = os.environ.get("DECEPTICON_NEO4J_PASSWORD", "").strip()
        database = os.environ.get("DECEPTICON_NEO4J_DATABASE", "neo4j").strip() or "neo4j"

        missing: list[str] = []
        if not uri:
            missing.append("DECEPTICON_NEO4J_URI")
        if not user:
            missing.append("DECEPTICON_NEO4J_USER")
        if not password:
            missing.append("DECEPTICON_NEO4J_PASSWORD")

        if missing:
            joined = ", ".join(missing)
            raise Neo4jUnavailableError(
                f"Neo4j backend selected but missing environment variables: {joined}"
            )

        return cls(uri=uri, user=user, password=password, database=database)


def _decode_props(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _encode_props(props: dict[str, Any]) -> str:
    try:
        return json.dumps(props, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


class Neo4jStore:
    """Load/query/upsert knowledge graph nodes and edges in Neo4j.

    All writes use MERGE-based upserts with native Neo4j labels
    (one label per NodeKind) and native relationship types (one type
    per EdgeKind).
    """

    def __init__(self, config: Neo4jConfig) -> None:
        try:
            from neo4j import GraphDatabase
        except Exception as exc:  # pragma: no cover - exercised in integration envs
            raise Neo4jUnavailableError(
                "Neo4j backend requires the `neo4j` Python package. Install it and retry."
            ) from exc

        self._driver = GraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
        )
        self._database = config.database

    @classmethod
    def from_env(cls) -> Neo4jStore:
        return cls(Neo4jConfig.from_env())

    def close(self) -> None:
        self._driver.close()

    # ── Schema initialization ────────────────────────────────────────────

    def ensure_schema(self) -> None:
        """Create constraints and indexes if they don't exist.

        Runs the full set of uniqueness constraints and performance indexes
        from the attack-graph-schema.md design document (Section 5).
        """
        constraints = [
            "CREATE CONSTRAINT host_ip IF NOT EXISTS FOR (h:Host) REQUIRE h.ip IS UNIQUE",
            "CREATE CONSTRAINT domain_fqdn IF NOT EXISTS FOR (d:Domain) REQUIRE d.fqdn IS UNIQUE",
            "CREATE CONSTRAINT network_cidr IF NOT EXISTS FOR (n:Network) REQUIRE n.cidr IS UNIQUE",
            "CREATE CONSTRAINT service_key IF NOT EXISTS FOR (s:Service) REQUIRE s.key IS UNIQUE",
            "CREATE CONSTRAINT url_normalized IF NOT EXISTS FOR (u:URL) REQUIRE u.url IS UNIQUE",
            "CREATE CONSTRAINT user_key IF NOT EXISTS FOR (u:User) REQUIRE u.key IS UNIQUE",
            "CREATE CONSTRAINT cve_id IF NOT EXISTS FOR (c:CVE) REQUIRE c.cve_id IS UNIQUE",
            "CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (w:Weakness) REQUIRE w.cwe_id IS UNIQUE",
            (
                "CREATE CONSTRAINT technique_id IF NOT EXISTS"
                " FOR (t:Technique) REQUIRE t.technique_id IS UNIQUE"
            ),
            (
                "CREATE CONSTRAINT vuln_key IF NOT EXISTS"
                " FOR (v:Vulnerability) REQUIRE v.key IS UNIQUE"
            ),
            ("CREATE CONSTRAINT finding_key IF NOT EXISTS FOR (f:Finding) REQUIRE f.key IS UNIQUE"),
            (
                "CREATE CONSTRAINT credential_key IF NOT EXISTS"
                " FOR (c:Credential) REQUIRE c.key IS UNIQUE"
            ),
            (
                "CREATE CONSTRAINT cloud_arn IF NOT EXISTS"
                " FOR (cr:CloudResource) REQUIRE cr.arn IS UNIQUE"
            ),
            (
                "CREATE CONSTRAINT contract_addr IF NOT EXISTS"
                " FOR (c:Contract) REQUIRE c.address IS UNIQUE"
            ),
            (
                "CREATE CONSTRAINT attack_path_key IF NOT EXISTS"
                " FOR (ap:AttackPath) REQUIRE ap.key IS UNIQUE"
            ),
        ]

        indexes = [
            "CREATE INDEX host_explored IF NOT EXISTS FOR (h:Host) ON (h.explored)",
            "CREATE INDEX host_compromised IF NOT EXISTS FOR (h:Host) ON (h.compromised)",
            (
                "CREATE INDEX service_product IF NOT EXISTS"
                " FOR (s:Service) ON (s.product, s.version)"
            ),
            "CREATE INDEX vuln_severity IF NOT EXISTS FOR (v:Vulnerability) ON (v.severity)",
            "CREATE INDEX vuln_validated IF NOT EXISTS FOR (v:Vulnerability) ON (v.validated)",
            "CREATE INDEX vuln_class IF NOT EXISTS FOR (v:Vulnerability) ON (v.vuln_class)",
            "CREATE INDEX finding_status IF NOT EXISTS FOR (f:Finding) ON (f.status)",
            "CREATE INDEX candidate_status IF NOT EXISTS FOR (c:Candidate) ON (c.status)",
            "CREATE INDEX credential_cracked IF NOT EXISTS FOR (c:Credential) ON (c.cracked)",
            "CREATE INDEX technique_tactic IF NOT EXISTS FOR (t:Technique) ON (t.tactic)",
            "CREATE INDEX user_admin IF NOT EXISTS FOR (u:User) ON (u.admin)",
        ]

        with self._driver.session(database=self._database) as session:
            for stmt in constraints:
                session.run(stmt)
            for stmt in indexes:
                session.run(stmt)

        log.info("Neo4j schema constraints and indexes ensured")

    # ── Revision ─────────────────────────────────────────────────────────

    def revision(self) -> float:
        """Return a monotonic-ish revision token for cache invalidation.

        Scans all individual node labels rather than the old KGNode label.
        """
        # Build a UNION query across all known node labels to find max updated_at
        label_clauses = " UNION ALL ".join(
            f"MATCH (n:{label}) RETURN coalesce(max(n.updated_at), 0.0) AS rev"
            for label in _ALL_NODE_LABELS
        )
        query = f"""
        CALL {{
          {label_clauses}
        }}
        WITH max(rev) AS node_rev
        RETURN coalesce(node_rev, 0.0) AS rev
        """
        with self._driver.session(database=self._database) as session:
            record = session.run(query).single()
        if record is None:
            return 0.0
        try:
            return float(record.get("rev", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    # ── Single upserts ───────────────────────────────────────────────────

    def upsert_node(self, node: Node) -> None:
        """MERGE a node using its NodeKind as the Neo4j label."""
        label = _label_for(node.kind)
        now = time.time()
        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n.kind = $kind,
            n.label = $label,
            n.props = $props,
            n.key = $key,
            n.created_at = coalesce(n.created_at, $created_at),
            n.updated_at = $updated_at
        """
        params = {
            "id": node.id,
            "kind": node.kind.value,
            "label": node.label,
            "props": _encode_props(node.props),
            "key": node.props.get("key", node.id),
            "created_at": node.created_at,
            "updated_at": now,
        }
        with self._driver.session(database=self._database) as session:
            session.run(query, params)

    def upsert_edge(self, edge: Edge) -> None:
        """MERGE a relationship using its EdgeKind as the Neo4j relationship type."""
        rel_type = edge.kind.value.upper()
        # Match src and dst nodes by id across all labels (no label constraint)
        query = f"""
        MATCH (src {{id: $src_id}}), (dst {{id: $dst_id}})
        MERGE (src)-[r:{rel_type} {{id: $edge_id}}]->(dst)
        SET r.kind = $kind,
            r.weight = $weight,
            r.props = $props,
            r.created_at = coalesce(r.created_at, $created_at)
        """
        params = {
            "src_id": edge.src,
            "dst_id": edge.dst,
            "edge_id": edge.id,
            "kind": edge.kind.value,
            "weight": edge.weight,
            "props": _encode_props(edge.props),
            "created_at": edge.created_at,
        }
        with self._driver.session(database=self._database) as session:
            session.run(query, params)

    # ── Batch upserts ────────────────────────────────────────────────────

    def batch_upsert_nodes(self, nodes: list[Node]) -> int:
        """Batch MERGE nodes grouped by label for efficiency.

        Groups nodes by kind, then uses UNWIND per group so Neo4j can
        batch-process MERGE operations.
        """
        if not nodes:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        now = time.time()
        for node in nodes:
            label = _label_for(node.kind)
            grouped[label].append(
                {
                    "id": node.id,
                    "kind": node.kind.value,
                    "label": node.label,
                    "props": _encode_props(node.props),
                    "key": node.props.get("key", node.id),
                    "created_at": node.created_at,
                    "updated_at": now,
                }
            )

        total = 0
        with self._driver.session(database=self._database) as session:
            for label, batch in grouped.items():
                query = f"""
                UNWIND $batch AS row
                MERGE (n:{label} {{id: row.id}})
                SET n.kind = row.kind,
                    n.label = row.label,
                    n.props = row.props,
                    n.key = row.key,
                    n.created_at = coalesce(n.created_at, row.created_at),
                    n.updated_at = row.updated_at
                """
                session.run(query, batch=batch)
                total += len(batch)

        return total

    def batch_upsert_edges(self, edges: list[Edge]) -> int:
        """Batch MERGE edges grouped by relationship type for efficiency.

        Groups edges by kind, then uses UNWIND per group so Neo4j can
        batch-process MERGE operations.
        """
        if not edges:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            rel_type = edge.kind.value.upper()
            grouped[rel_type].append(
                {
                    "id": edge.id,
                    "kind": edge.kind.value,
                    "src_id": edge.src,
                    "dst_id": edge.dst,
                    "weight": edge.weight,
                    "props": _encode_props(edge.props),
                    "created_at": edge.created_at,
                }
            )

        total = 0
        with self._driver.session(database=self._database) as session:
            for rel_type, batch in grouped.items():
                query = f"""
                UNWIND $batch AS row
                MATCH (src {{id: row.src_id}}), (dst {{id: row.dst_id}})
                MERGE (src)-[r:{rel_type} {{id: row.id}}]->(dst)
                SET r.kind = row.kind,
                    r.weight = row.weight,
                    r.props = row.props,
                    r.created_at = coalesce(r.created_at, row.created_at)
                """
                session.run(query, batch=batch)
                total += len(batch)

        return total

    # ── Queries ──────────────────────────────────────────────────────────

    def query_neighbors(
        self,
        node_id: str,
        edge_kind: str | None = None,
        direction: str = "out",
    ) -> list[dict[str, Any]]:
        """Query neighbors of a node using Cypher, optionally filtering by edge kind.

        direction: "out" (outgoing), "in" (incoming), or "both".
        Returns a list of dicts with edge and neighbor node properties.
        """
        if direction not in ("out", "in", "both"):
            raise ValueError("direction must be out/in/both")

        if direction == "out":
            pattern = "(src {id: $node_id})-[r]->(nbr)"
        elif direction == "in":
            pattern = "(nbr)-[r]->(src {id: $node_id})"
        else:
            pattern = "(src {id: $node_id})-[r]-(nbr)"

        where_clause = ""
        if edge_kind:
            where_clause = f"WHERE type(r) = '{edge_kind.upper()}'"

        query = f"""
        MATCH {pattern}
        {where_clause}
        RETURN nbr.id AS id,
               nbr.kind AS kind,
               nbr.label AS label,
               coalesce(nbr.props, '{{}}') AS props,
               coalesce(nbr.created_at, 0.0) AS created_at,
               coalesce(nbr.updated_at, 0.0) AS updated_at,
               r.id AS edge_id,
               type(r) AS edge_type,
               r.kind AS edge_kind,
               coalesce(r.weight, 1.0) AS edge_weight,
               coalesce(r.props, '{{}}') AS edge_props
        """
        results: list[dict[str, Any]] = []
        with self._driver.session(database=self._database) as session:
            for row in session.run(query, node_id=node_id):
                results.append(
                    {
                        "node": {
                            "id": row["id"],
                            "kind": row["kind"],
                            "label": row["label"],
                            "props": _decode_props(row["props"]),
                            "created_at": float(row["created_at"] or 0.0),
                            "updated_at": float(row["updated_at"] or 0.0),
                        },
                        "edge": {
                            "id": row["edge_id"],
                            "type": row["edge_type"],
                            "kind": row["edge_kind"],
                            "weight": float(row["edge_weight"] or 1.0),
                            "props": _decode_props(row["edge_props"]),
                        },
                    }
                )
        return results

    def query_by_kind(self, kind: str) -> list[dict[str, Any]]:
        """Query all nodes of a given kind using native Neo4j labels.

        ``kind`` can be either a NodeKind value (e.g. "host") or a Neo4j
        label (e.g. "Host"). Both are accepted.
        """
        # Resolve kind to a Neo4j label
        try:
            nk = NodeKind(kind)
            label = _label_for(nk)
        except ValueError:
            # Maybe it's already a label name (PascalCase)
            label = kind if kind in _ALL_NODE_LABELS else kind

        query = f"""
        MATCH (n:{label})
        RETURN n.id AS id,
               n.kind AS kind,
               n.label AS label,
               coalesce(n.props, '{{}}') AS props,
               coalesce(n.created_at, 0.0) AS created_at,
               coalesce(n.updated_at, 0.0) AS updated_at
        """
        results: list[dict[str, Any]] = []
        with self._driver.session(database=self._database) as session:
            for row in session.run(query):
                results.append(
                    {
                        "id": row["id"],
                        "kind": row["kind"],
                        "label": row["label"],
                        "props": _decode_props(row["props"]),
                        "created_at": float(row["created_at"] or 0.0),
                        "updated_at": float(row["updated_at"] or 0.0),
                    }
                )
        return results

    def query_custom(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a raw Cypher query and return results as list of dicts.

        Intended for agent tools that need ad-hoc graph queries (attack path
        analysis, neighbor traversal, etc.).
        """
        results: list[dict[str, Any]] = []
        with self._driver.session(database=self._database) as session:
            for record in session.run(cypher, parameters=params or {}):
                results.append(dict(record))
        return results

    def stats(self) -> dict[str, int]:
        """Count nodes and edges by label/type.

        Returns a dict with keys like "nodes", "edges", "node.Host",
        "edge.HAS_VULN" etc.
        """
        counts: dict[str, int] = {"nodes": 0, "edges": 0}

        # Count nodes per label
        for label in _ALL_NODE_LABELS:
            query = f"MATCH (n:{label}) RETURN count(n) AS cnt"
            with self._driver.session(database=self._database) as session:
                record = session.run(query).single()
                cnt = int(record["cnt"]) if record else 0
            if cnt > 0:
                counts[f"node.{label}"] = cnt
                counts["nodes"] += cnt

        # Count edges per relationship type
        edge_query = """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(r) AS cnt
        """
        with self._driver.session(database=self._database) as session:
            for row in session.run(edge_query):
                rel_type = row["rel_type"]
                cnt = int(row["cnt"])
                if cnt > 0:
                    counts[f"edge.{rel_type}"] = cnt
                    counts["edges"] += cnt

        return counts

    def remove_node(self, node_id: str) -> int:
        """DETACH DELETE a node by id (removes the node and all its relationships).

        Returns the number of entities removed (node + detached relationships).
        """
        query = """
        MATCH (n {id: $node_id})
        OPTIONAL MATCH (n)-[r]-()
        WITH n, collect(r) AS rels
        DETACH DELETE n
        RETURN 1 + size(rels) AS removed
        """
        with self._driver.session(database=self._database) as session:
            record = session.run(query, node_id=node_id).single()
        if record is None:
            return 0
        return int(record["removed"])

    # ── Backward-compatible full-graph load ──────────────────────────────

    def load_graph(self) -> KnowledgeGraph:
        """Load the entire graph into a KnowledgeGraph Pydantic model.

        Queries by individual labels (not the old KGNode label).
        Kept for backward compatibility during migration, used by tests
        and one-shot operations.
        """
        graph = KnowledgeGraph()

        # Load nodes across all known labels
        with self._driver.session(database=self._database) as session:
            for label in _ALL_NODE_LABELS:
                node_query = f"""
                MATCH (n:{label})
                RETURN n.id AS id,
                       n.kind AS kind,
                       n.label AS label,
                       coalesce(n.props, '{{}}') AS props,
                       coalesce(n.created_at, 0.0) AS created_at,
                       coalesce(n.updated_at, 0.0) AS updated_at
                """
                for row in session.run(node_query):
                    node_id = row.get("id")
                    kind_raw = row.get("kind")
                    if not isinstance(node_id, str) or not isinstance(kind_raw, str):
                        continue
                    try:
                        kind = NodeKind(kind_raw)
                    except ValueError:
                        log.warning(
                            "Skipping Neo4j node with unknown kind",
                            extra={"id": node_id, "kind": kind_raw},
                        )
                        continue

                    node = Node(
                        id=node_id,
                        kind=kind,
                        label=str(row.get("label") or node_id),
                        props=_decode_props(row.get("props")),
                        created_at=float(row.get("created_at") or 0.0),
                        updated_at=float(row.get("updated_at") or 0.0),
                    )
                    graph.nodes[node.id] = node

            # Load all edges (match any relationship type)
            edge_query = """
            MATCH (src)-[r]->(dst)
            WHERE r.id IS NOT NULL
            RETURN r.id AS id,
                   src.id AS src,
                   dst.id AS dst,
                   r.kind AS kind,
                   coalesce(r.weight, 1.0) AS weight,
                   coalesce(r.props, '{}') AS props,
                   coalesce(r.created_at, 0.0) AS created_at
            """
            for row in session.run(edge_query):
                edge_id = row.get("id")
                kind_raw = row.get("kind")
                src = row.get("src")
                dst = row.get("dst")
                if (
                    not isinstance(edge_id, str)
                    or not isinstance(kind_raw, str)
                    or not isinstance(src, str)
                    or not isinstance(dst, str)
                ):
                    continue
                if src not in graph.nodes or dst not in graph.nodes:
                    continue
                try:
                    kind = EdgeKind(kind_raw)
                except ValueError:
                    log.warning(
                        "Skipping Neo4j edge with unknown kind",
                        extra={"id": edge_id, "kind": kind_raw},
                    )
                    continue

                edge = Edge(
                    id=edge_id,
                    src=src,
                    dst=dst,
                    kind=kind,
                    weight=float(row.get("weight") or 1.0),
                    props=_decode_props(row.get("props")),
                    created_at=float(row.get("created_at") or 0.0),
                )
                graph.edges[edge.id] = edge

        return graph
