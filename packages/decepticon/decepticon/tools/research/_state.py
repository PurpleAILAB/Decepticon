"""Legacy compat shim — KGStore-backed implementation of the old
``Neo4jStore`` surface.

The old ``Neo4jStore`` class (``tools/research/neo4j_store.py``) is
removed in this PR. Every caller that still imports from
``decepticon.tools.research._state`` — AD_TOOLS, CONTRACT_TOOLS,
RESEARCH_TOOLS, ``chain.py``, ``health.py``, ``dedupe.py`` — now sits
on top of the new ``KGStore`` (``decepticon.middleware.kg_internal.store``)
through this shim. The agent-facing ``_load`` / ``_save`` /
``graph_transaction`` calling convention is preserved bit-for-bit, so
the old tool surface keeps working while individual tools migrate to
direct ``KGStore.record_observations`` calls in dedicated follow-up
PRs (BloodHound and Slither in particular need schema research before
their direct migration is safe — see
``docs/design/2026-06-03-kg-middleware-redesign.md``).

What the shim guarantees:

  - Engagement scoping is read from the
    ``EngagementContextMiddleware`` contextvar
    (``decepticon_core.utils.engagement_scope.get_active_engagement``).
    Reads / writes route through ``KGStore`` with that engagement.
  - The legacy ``Node`` SHA1 id is preserved on every persisted node
    under the ``_legacy_id`` property so edge upserts (which carry
    ``src``/``dst`` as the SHA1) keep working — and the load path in
    ``reporting/kg_adapter`` restores it onto ``Node.id``.
  - All schema work (constraints + indexes) is owned by ``KGStore``'s
    migration runner. The shim never touches the schema directly.
"""

from __future__ import annotations

import contextlib
import functools
import json
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from decepticon.middleware.kg_internal.store import (
    KGStore,
    KGStoreConfigError,
    KGStoreUnavailableError,
)
from decepticon.tools.reporting.kg_adapter import load_engagement_graph
from decepticon.tools.research._engagement_scope import _LEGACY_ENGAGEMENT_LABEL
from decepticon_core.types.kg import Edge, KnowledgeGraph, Node
from decepticon_core.utils.engagement_scope import get_active_engagement
from decepticon_core.utils.logging import get_logger

log = get_logger("research.state")

_GRAPH_LOCK = threading.Lock()
_store: _LegacyStoreShim | None = None


def _resolve_engagement() -> str:
    return get_active_engagement() or _LEGACY_ENGAGEMENT_LABEL


def _node_to_observation(node: Node) -> dict[str, Any]:
    """Translate an in-memory ``Node`` into a KGStore observation dict.

    The legacy ``Node.id`` (SHA1 of ``kind::key``) is stored under the
    reserved-but-non-provenance ``_legacy_id`` property so callers that
    later look up the node by SHA1 (typically through ``Edge.src`` /
    ``Edge.dst``) can resolve it.
    """
    explicit_key = node.props.get("key") or node.label
    props = {k: v for k, v in node.props.items() if k != "key"}
    props["_legacy_id"] = node.id
    return {
        "kind": node.kind.value,
        "key": str(explicit_key),
        "label": node.label,
        "props": props,
    }


class _LegacyStoreShim:
    """Wraps :class:`KGStore` with the legacy ``Neo4jStore`` interface.

    Only the methods the existing tool code actually calls are
    implemented — ``query_custom`` (raw Cypher reads from ``chain.py``),
    ``revision`` / ``stats`` (``health.py``), ``load_graph``,
    ``upsert_node`` / ``upsert_edge``, and the batch variants. Other
    methods that the old ``Neo4jStore`` exposed but no in-tree caller
    used are intentionally absent.
    """

    def __init__(self, kgstore: KGStore) -> None:
        self._kgstore = kgstore

    def close(self) -> None:
        self._kgstore.close()

    def query_custom(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Raw read-only Cypher passthrough.

        Engagement scoping is the caller's responsibility — pass
        ``$engagement`` (auto-injected here as ``_resolve_engagement``)
        in the query's ``WHERE`` clause if scoping matters. Callers
        that ignore scoping (e.g. legacy ``chain.py`` Cypher) get the
        same un-filtered behaviour the old Neo4jStore had.
        """
        engagement = _resolve_engagement()
        merged: dict[str, Any] = {"engagement": engagement, **(params or {})}
        return self._kgstore.execute_read(query, merged, engagement=engagement)

    def revision(self) -> float:
        """Opaque mutation marker — used by ``health.py``."""
        engagement = _resolve_engagement()
        rows = self._kgstore.execute_read(
            (
                "MATCH (n) WHERE n.engagement = $engagement "
                "RETURN coalesce(max(n.lastupdated), 0.0) AS rev"
            ),
            {"engagement": engagement},
            engagement=engagement,
        )
        if not rows:
            return 0.0
        return float(rows[0].get("rev") or 0.0)

    def stats(self) -> dict[str, int]:
        """Node / edge counts — used by ``health.py``."""
        engagement = _resolve_engagement()
        node_rows = self._kgstore.execute_read(
            "MATCH (n) WHERE n.engagement = $engagement RETURN count(n) AS c",
            {"engagement": engagement},
            engagement=engagement,
        )
        edge_rows = self._kgstore.execute_read(
            "MATCH ()-[r]->() WHERE r.engagement = $engagement RETURN count(r) AS c",
            {"engagement": engagement},
            engagement=engagement,
        )
        return {
            "nodes": int((node_rows or [{"c": 0}])[0].get("c") or 0),
            "edges": int((edge_rows or [{"c": 0}])[0].get("c") or 0),
        }

    def load_graph(self, *, all_engagements: bool = False) -> KnowledgeGraph:
        """Build a ``KnowledgeGraph`` for the active engagement.

        ``all_engagements`` is preserved for signature compatibility
        but is currently a no-op — every legacy caller in the tree
        loads within its engagement context, and ``KGStore`` always
        scopes by engagement.
        """
        _ = all_engagements  # accepted for compat, ignored
        return load_engagement_graph(_resolve_engagement())

    def upsert_node(self, node: Node) -> None:
        """Persist one node via ``record_observations``."""
        engagement = _resolve_engagement()
        self._kgstore.record_observations(
            [_node_to_observation(node)],
            engagement=engagement,
            created_by="legacy_shim",
            source_episode_id="legacy",
        )

    def upsert_edge(self, edge: Edge) -> None:
        """Persist one edge.

        ``record_observations`` only accepts edges attached to a node
        observation, so this path runs raw Cypher with the same
        ``MERGE`` + provenance pattern KGStore uses internally. The
        source / destination are matched by ``_legacy_id`` — the SHA1
        that ``_node_to_observation`` stored on every node.
        """
        engagement = _resolve_engagement()
        edge_kind = edge.kind.value
        now = time.time()
        self._kgstore.execute_write(
            (
                f"MATCH (s) WHERE s.engagement = $engagement AND s._legacy_id = $src "
                f"MATCH (d) WHERE d.engagement = $engagement AND d._legacy_id = $dst "
                f"MERGE (s)-[r:{edge_kind} {{key: $edge_key, engagement: $engagement}}]->(d) "
                "ON CREATE SET r.firstseen = $now, r.lastupdated = $now, "
                "  r.weight = $weight, r.created_by = $created_by, "
                "  r.source_episode_id = $sep, r += $props "
                "ON MATCH SET r.lastupdated = $now, r.weight = $weight"
            ),
            {
                "engagement": engagement,
                "src": edge.src,
                "dst": edge.dst,
                "edge_key": edge.id,
                "weight": edge.weight,
                "props": dict(edge.props),
                "now": now,
                "created_by": "legacy_shim",
                "sep": "legacy",
            },
            engagement=engagement,
        )

    def batch_upsert_nodes(self, nodes: list[Node]) -> int:
        if not nodes:
            return 0
        engagement = _resolve_engagement()
        observations = [_node_to_observation(n) for n in nodes]
        self._kgstore.record_observations(
            observations,
            engagement=engagement,
            created_by="legacy_shim",
            source_episode_id="legacy",
        )
        return len(nodes)

    def batch_upsert_edges(self, edges: list[Edge]) -> int:
        if not edges:
            return 0
        for edge in edges:
            self.upsert_edge(edge)
        return len(edges)


def get_store() -> _LegacyStoreShim:
    """Singleton legacy-compat shim. First call constructs the
    underlying :class:`KGStore` from environment variables."""
    global _store
    if _store is None:
        _store = _LegacyStoreShim(KGStore.from_env())
    return _store


def close_store() -> None:
    """Close the underlying KGStore and drop the shim singleton."""
    global _store
    if _store is not None:
        with contextlib.suppress(Exception):
            _store.close()
        _store = None


# ── Compat wrappers ──────────────────────────────────────────────────
#
# ``_load`` / ``_save`` / ``graph_transaction`` preserve the old
# call shape so tool code under ``tools/ad``, ``tools/contracts``,
# and ``tools/research/{tools,patch,scanner_tools,bounty,dedupe}.py``
# does not need to change in this PR.

_COMPAT_PATH = Path("/dev/null")


def _load() -> tuple[KnowledgeGraph, Path]:
    """Load the engagement KG. Returns ``(KnowledgeGraph, Path)`` for
    backward compatibility — the ``Path`` is an unused placeholder."""
    return get_store().load_graph(), _COMPAT_PATH


def _save(graph: KnowledgeGraph, path: Any = None) -> None:
    """Persist a KnowledgeGraph to the engagement KG via
    ``record_observations`` + per-edge ``MERGE``. ``path`` is ignored."""
    _ = path
    store = get_store()
    nodes = list(graph.nodes.values())
    edges = list(graph.edges.values())
    if nodes:
        store.batch_upsert_nodes(nodes)
    if edges:
        store.batch_upsert_edges(edges)


def _kg_backend_name() -> str:
    """Always returns 'neo4j' — preserved for compat with the older
    ``backend_health`` tool that surfaced this string to operators."""
    return "neo4j"


def _json(data: Any) -> str:
    """Compact-ish JSON serializer used by tool return values."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


_KG_UNAVAILABLE_GUIDANCE = (
    "The knowledge-graph backend is not configured for this run (no reachable "
    "Neo4j). Do NOT retry kg_* tools — record this observation to a workspace "
    "file instead (e.g. write it into your findings / recon notes)."
)


def kg_degrades(fn: Callable[..., str]) -> Callable[..., str]:
    """Wrap a ``kg_*`` @tool body so a missing/unreachable KGStore returns a
    graceful message instead of raising.

    The KG middleware *slot* (:func:`decepticon.agents.middleware_slots._make_kg`)
    already degrades when ``DECEPTICON_NEO4J_*`` is unset, but agents such as
    ``osint_operator`` import the ``kg_*`` tools DIRECTLY into their tool set,
    bypassing that guard — so a call would raise ``KGStoreConfigError`` from
    ``get_store()`` and surface as a hard tool error. This mirrors the slot
    guard at the tool layer: the agent is told the KG is unavailable and to
    write findings to files, and adapts, rather than looping on a dead backend.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except (KGStoreConfigError, KGStoreUnavailableError) as exc:
            return _json(
                {
                    "error": "knowledge_graph_unavailable",
                    "detail": str(exc),
                    "guidance": _KG_UNAVAILABLE_GUIDANCE,
                }
            )

    return wrapper


@contextmanager
def graph_transaction():
    """Locked read-modify-save context.

    Yields the engagement's ``KnowledgeGraph``; persists it back to
    ``KGStore`` on exit. The Python lock keeps writes inside a single
    process sequential — ``KGStore`` provides Neo4j-level atomicity
    per save call.
    """
    with _GRAPH_LOCK:
        graph, path = _load()
        yield graph
        _save(graph, path)
