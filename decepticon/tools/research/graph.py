"""KnowledgeGraph — persistent vulnerability research graph.

Survives Ralph fresh-iteration resets by serialising to JSON on disk by
default (``/workspace/kg.json`` inside the sandbox, bind-mounted to the
host). The runtime persistence backend can be swapped to Neo4j via
``decepticon.research._state`` environment configuration.

Schema
------
Nodes have a ``kind`` (Host, Service, Vulnerability, Credential, Secret,
Finding, CodeLocation, Chain, Entrypoint, CrownJewel) and a free-form
``props`` dict. Edges carry a ``kind`` (runs_on, exposes, has_vuln,
auth_as, enables, leaks, chains_to, located_at, reaches) plus optional
``weight`` used by the chain planner (lower = easier exploitation).

Design goals
------------
1. **Append-mostly**: agents write once, read often. Deduplication via
   deterministic node IDs (SHA1 of kind + canonical key).
2. **Concurrent safety**: file-lock-free atomic replace (write-tmp + rename).
   The graph is small enough to rewrite in full on each mutation.
3. **Schema validation**: Pydantic models reject bad writes at the boundary.
4. **Queryable**: ``neighbors()``, ``by_kind()``, ``find()`` avoid the need
   for a real graph database. O(N) is fine at engagement scale (<10K nodes).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Iterable, Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ── Enumerations ────────────────────────────────────────────────────────


class NodeKind(StrEnum):
    """Canonical node types in the research graph."""

    HOST = "host"
    SERVICE = "service"
    URL = "url"
    REPO = "repo"
    FILE = "file"
    CODE_LOCATION = "code_location"
    VULNERABILITY = "vulnerability"
    CVE = "cve"
    FINDING = "finding"
    CREDENTIAL = "credential"
    SECRET = "secret"
    USER = "user"
    ENTRYPOINT = "entrypoint"
    CROWN_JEWEL = "crown_jewel"
    CHAIN = "chain"
    HYPOTHESIS = "hypothesis"
    CANDIDATE = "candidate"  # scanner-emitted suspect code location
    PATCH = "patch"  # proposed/applied fix for a verified finding


class EdgeKind(StrEnum):
    """Canonical edge types — describe how nodes relate."""

    RUNS_ON = "runs_on"  # service → host
    EXPOSES = "exposes"  # host → service/url
    HAS_VULN = "has_vuln"  # service/url/file → vulnerability
    DEFINED_IN = "defined_in"  # vuln → code_location
    LOCATED_AT = "located_at"  # code_location → file/repo
    AFFECTED_BY = "affected_by"  # service → cve
    MAPPED_TO = "mapped_to"  # finding → vulnerability/cve
    AUTH_AS = "auth_as"  # credential → user
    GRANTS = "grants"  # credential → host/service
    LEAKS = "leaks"  # vulnerability → secret/credential
    ENABLES = "enables"  # vulnerability → vulnerability (pivot)
    CHAINS_TO = "chains_to"  # finding → finding (ordered step)
    REACHES = "reaches"  # chain → crown_jewel
    STARTS_AT = "starts_at"  # chain → entrypoint
    CONTAINS = "contains"  # chain → finding (unordered member)
    VALIDATES = "validates"  # poc → finding/vulnerability
    DERIVED_FROM = "derived_from"  # vulnerability → candidate
    PATCHES = "patches"  # patch → vulnerability/finding


class Severity(StrEnum):
    """CVSS-style qualitative severity."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_SCORE: dict[Severity, float] = {
    Severity.INFO: 0.0,
    Severity.LOW: 3.0,
    Severity.MEDIUM: 5.5,
    Severity.HIGH: 7.5,
    Severity.CRITICAL: 9.5,
}


# ── Models ──────────────────────────────────────────────────────────────


class Node(BaseModel):
    """A node in the knowledge graph."""

    id: str
    kind: NodeKind
    label: str
    props: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @classmethod
    def make(cls, kind: NodeKind, label: str, **props: Any) -> Node:
        """Construct a node with a deterministic ID derived from ``kind + label``.

        Same (kind, label) always hashes to the same ID — this is how we
        dedupe agent writes without needing a database. ``props`` contributes
        to the hash only through the ``key`` field if provided, letting
        callers supply an explicit dedup key (e.g. normalized URL).
        """
        key = props.get("key", label)
        digest = hashlib.sha1(f"{kind.value}::{key}".encode()).hexdigest()[:16]
        return cls(id=digest, kind=kind, label=label, props=dict(props))


class Edge(BaseModel):
    """A directed edge in the knowledge graph."""

    id: str
    src: str
    dst: str
    kind: EdgeKind
    weight: float = 1.0
    props: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    @classmethod
    def make(
        cls,
        src: str,
        dst: str,
        kind: EdgeKind,
        weight: float = 1.0,
        **props: Any,
    ) -> Edge:
        # ``key`` in props participates in the deterministic edge ID so
        # multiple edges of the same kind between the same (src, dst)
        # can coexist (e.g. AD GetChanges + GetChangesAll both mapped
        # to LEAKS but semantically distinct).
        key = props.get("key", "")
        digest = hashlib.sha1(f"{src}->{kind.value}->{dst}::{key}".encode()).hexdigest()[:16]
        return cls(id=digest, src=src, dst=dst, kind=kind, weight=weight, props=dict(props))


# ── Graph ───────────────────────────────────────────────────────────────

DEFAULT_PATH = Path("/workspace/kg.json")


class KnowledgeGraph(BaseModel):
    """Persistent engagement knowledge graph.

    Instances are intentionally loaded fresh from disk on each mutation
    (via :func:`load_graph` / :func:`save_graph`) so concurrent agents
    never stomp each other's writes with stale in-memory state.
    """

    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: dict[str, Edge] = Field(default_factory=dict)
    version: int = 1

    # ── mutators ──────────────────────────────────────────────────────

    def upsert_node(self, node: Node) -> Node:
        """Insert or update a node, merging props on update."""
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node
        # Merge — new props win, but keep created_at
        merged_props = {**existing.props, **node.props}
        existing.props = merged_props
        existing.label = node.label  # accept relabel
        existing.updated_at = time.time()
        return existing

    def upsert_edge(self, edge: Edge) -> Edge:
        """Insert or update an edge (weight is overwritten on re-insert)."""
        existing = self.edges.get(edge.id)
        if existing is None:
            self.edges[edge.id] = edge
            return edge
        existing.weight = edge.weight
        existing.props = {**existing.props, **edge.props}
        return existing

    def remove_node(self, node_id: str) -> int:
        """Remove a node and all edges touching it. Returns total removed count."""
        removed = 0
        if node_id in self.nodes:
            del self.nodes[node_id]
            removed += 1
        to_drop = [eid for eid, e in self.edges.items() if e.src == node_id or e.dst == node_id]
        for eid in to_drop:
            del self.edges[eid]
            removed += 1
        return removed

    # ── queries ───────────────────────────────────────────────────────

    def by_kind(self, kind: NodeKind) -> list[Node]:
        """All nodes of the given kind, ordered by creation time."""
        return sorted(
            (n for n in self.nodes.values() if n.kind == kind),
            key=lambda n: n.created_at,
        )

    def find(self, kind: NodeKind | None = None, **props: Any) -> list[Node]:
        """Find nodes matching kind and all provided prop equality constraints."""
        matches: list[Node] = []
        for node in self.nodes.values():
            if kind is not None and node.kind != kind:
                continue
            if all(node.props.get(k) == v for k, v in props.items()):
                matches.append(node)
        return matches

    def neighbors(
        self,
        node_id: str,
        edge_kind: EdgeKind | None = None,
        direction: str = "out",
    ) -> list[tuple[Edge, Node]]:
        """Return (edge, neighbor) pairs for a node.

        direction: "out" (src=node), "in" (dst=node), or "both".
        """
        if direction not in ("out", "in", "both"):
            raise ValueError("direction must be out/in/both")
        result: list[tuple[Edge, Node]] = []
        for edge in self.edges.values():
            if edge_kind is not None and edge.kind != edge_kind:
                continue
            if direction in ("out", "both") and edge.src == node_id:
                nbr = self.nodes.get(edge.dst)
                if nbr is not None:
                    result.append((edge, nbr))
            if direction in ("in", "both") and edge.dst == node_id:
                nbr = self.nodes.get(edge.src)
                if nbr is not None:
                    result.append((edge, nbr))
        return result

    def adjacency(self) -> dict[str, list[tuple[str, Edge]]]:
        """Build an adjacency list for graph search (out-edges only)."""
        adj: dict[str, list[tuple[str, Edge]]] = {nid: [] for nid in self.nodes}
        for edge in self.edges.values():
            if edge.src in adj and edge.dst in self.nodes:
                adj[edge.src].append((edge.dst, edge))
        return adj

    def stats(self) -> dict[str, int]:
        """High-level counts used for status displays and tests."""
        counts: dict[str, int] = {"nodes": len(self.nodes), "edges": len(self.edges)}
        for node in self.nodes.values():
            counts[f"node.{node.kind.value}"] = counts.get(f"node.{node.kind.value}", 0) + 1
        for edge in self.edges.values():
            counts[f"edge.{edge.kind.value}"] = counts.get(f"edge.{edge.kind.value}", 0) + 1
        return counts

    # ── severity helpers ──────────────────────────────────────────────

    def vulnerabilities_by_severity(self, min_severity: Severity = Severity.LOW) -> list[Node]:
        """Return vuln nodes with severity ≥ ``min_severity``, highest first."""
        threshold = SEVERITY_SCORE[min_severity]
        vulns: list[Node] = []
        for node in self.by_kind(NodeKind.VULNERABILITY):
            sev = Severity(node.props.get("severity", Severity.INFO))
            if SEVERITY_SCORE[sev] >= threshold:
                vulns.append(node)
        vulns.sort(
            key=lambda n: SEVERITY_SCORE[Severity(n.props.get("severity", Severity.INFO))],
            reverse=True,
        )
        return vulns

    # ── batch helpers ─────────────────────────────────────────────────

    def bulk_upsert_nodes(self, nodes: Iterable[Node]) -> int:
        count = 0
        for node in nodes:
            self.upsert_node(node)
            count += 1
        return count

    def bulk_upsert_edges(self, edges: Iterable[Edge]) -> int:
        count = 0
        for edge in edges:
            self.upsert_edge(edge)
            count += 1
        return count

    def iter_paths(self, src: str, dst: str, max_depth: int = 6) -> Iterator[list[str]]:
        """Enumerate simple paths from src to dst (bounded depth).

        Used by the chain planner for exploration but exposed here so
        callers can build custom scoring without pulling the planner in.
        """
        if src not in self.nodes or dst not in self.nodes:
            return
        adj = self.adjacency()
        stack: list[tuple[str, list[str]]] = [(src, [src])]
        while stack:
            cur, path = stack.pop()
            if len(path) > max_depth:
                continue
            if cur == dst and len(path) > 1:
                yield list(path)
                continue
            for nxt, _edge in adj.get(cur, []):
                if nxt in path:
                    continue
                stack.append((nxt, path + [nxt]))


# ── Persistence ─────────────────────────────────────────────────────────


def load_graph(path: Path | str = DEFAULT_PATH) -> KnowledgeGraph:
    """Load a graph from disk; return an empty one if the file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return KnowledgeGraph()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return KnowledgeGraph()
    return KnowledgeGraph.model_validate(raw)


def save_graph(graph: KnowledgeGraph, path: Path | str = DEFAULT_PATH) -> Path:
    """Atomically persist the graph to disk.

    Uses write-tmp + rename so a crash mid-write never corrupts the file.
    Parent directory is created on demand.

    Serialised without ``indent`` — the graph is machine-read on every
    @tool invocation (at 10k+ nodes this hits tens of MB of Pydantic
    validation). Compact output cuts parse time and disk I/O roughly
    in half. Set ``DECEPTICON_KG_INDENT=1`` to restore pretty-printing
    for human debugging.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("DECEPTICON_KG_INDENT"):
        payload = graph.model_dump_json(indent=2)
    else:
        payload = graph.model_dump_json()
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return p
