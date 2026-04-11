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
The initial migration strategy is "replace-all" on save: delete the current
``KGNode`` subgraph and reinsert from the in-memory model. This keeps behavior
identical to the JSON backend and is simple/reliable at current engagement
scales. It can be replaced with delta upserts later if needed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.tools.research.graph import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind

log = get_logger("research.neo4j")


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j backend is requested but not usable."""


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
                "Neo4j backend selected but missing environment variables: "
                f"{joined}"
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
    """Load/save :class:`KnowledgeGraph` from/to Neo4j."""

    def __init__(self, config: Neo4jConfig) -> None:
        try:
            from neo4j import GraphDatabase
        except Exception as exc:  # pragma: no cover - exercised in integration envs
            raise Neo4jUnavailableError(
                "Neo4j backend requires the `neo4j` Python package. "
                "Install it and retry."
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

    def revision(self) -> float:
        """Return a monotonic-ish revision token for cache invalidation."""
        query = """
        CALL {
          MATCH (n:KGNode)
          RETURN coalesce(max(n.updated_at), 0.0) AS node_rev
        }
        CALL {
          MATCH ()-[r:KG_EDGE]->()
          RETURN coalesce(max(r.created_at), 0.0) AS edge_rev
        }
        RETURN node_rev + edge_rev AS rev
        """
        with self._driver.session(database=self._database) as session:
            record = session.run(query).single()
        if record is None:
            return 0.0
        try:
            return float(record.get("rev", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def load_graph(self) -> KnowledgeGraph:
        graph = KnowledgeGraph()

        node_query = """
        MATCH (n:KGNode)
        RETURN n.id AS id,
               n.kind AS kind,
               n.label AS label,
               coalesce(n.props, "{}") AS props,
               coalesce(n.created_at, 0.0) AS created_at,
               coalesce(n.updated_at, 0.0) AS updated_at
        """
        edge_query = """
        MATCH (src:KGNode)-[r:KG_EDGE]->(dst:KGNode)
        RETURN r.id AS id,
               src.id AS src,
               dst.id AS dst,
               r.kind AS kind,
               coalesce(r.weight, 1.0) AS weight,
               coalesce(r.props, "{}") AS props,
               coalesce(r.created_at, 0.0) AS created_at
        """

        with self._driver.session(database=self._database) as session:
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

    def save_graph(self, graph: KnowledgeGraph) -> None:
        payload = graph.model_dump(mode="python")

        with self._driver.session(database=self._database) as session:
            session.execute_write(self._write_replace_all, payload)

    @staticmethod
    def _write_replace_all(tx, payload: dict[str, Any]) -> None:
        tx.run("MATCH (n:KGNode) DETACH DELETE n")

        nodes = payload.get("nodes", {})
        if isinstance(nodes, dict):
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                tx.run(
                    """
                    CREATE (n:KGNode {
                      id: $id,
                      kind: $kind,
                      label: $label,
                      props: $props,
                      created_at: $created_at,
                      updated_at: $updated_at
                    })
                    """,
                    id=node.get("id"),
                    kind=node.get("kind"),
                    label=node.get("label"),
                    props=_encode_props(node.get("props") or {}),
                    created_at=float(node.get("created_at") or 0.0),
                    updated_at=float(node.get("updated_at") or 0.0),
                )

        edges = payload.get("edges", {})
        if isinstance(edges, dict):
            for edge in edges.values():
                if not isinstance(edge, dict):
                    continue
                tx.run(
                    """
                    MATCH (src:KGNode {id: $src}), (dst:KGNode {id: $dst})
                    CREATE (src)-[:KG_EDGE {
                      id: $id,
                      kind: $kind,
                      weight: $weight,
                      props: $props,
                      created_at: $created_at
                    }]->(dst)
                    """,
                    id=edge.get("id"),
                    src=edge.get("src"),
                    dst=edge.get("dst"),
                    kind=edge.get("kind"),
                    weight=float(edge.get("weight") or 1.0),
                    props=_encode_props(edge.get("props") or {}),
                    created_at=float(edge.get("created_at") or 0.0),
                )
