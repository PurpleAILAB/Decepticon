"""Neo4j-only state management for the attack graph.

Provides a singleton Neo4jStore and convenience functions for
tool modules to access it.

Compatibility layer: ``_load()`` and ``_save()`` are preserved as
thin wrappers so the 40+ call sites in ``tools.py``, ``contracts/tools.py``,
``reporting/tools.py``, etc. continue to work without a mass rewrite.
They load/save through the Neo4j store instead of JSON files.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from decepticon.tools.research.neo4j_store import Neo4jStore
from decepticon_core.utils.logging import get_logger

log = get_logger("research.state")

_GRAPH_LOCK = threading.Lock()
_store: Neo4jStore | None = None


def get_store() -> Neo4jStore:
    """Return the singleton Neo4jStore, creating it on first call."""
    global _store
    if _store is None:
        _store = Neo4jStore.from_env()
        _store.ensure_schema()
    return _store


def close_store() -> None:
    """Close the Neo4j driver and clear the singleton."""
    global _store
    if _store is not None:
        try:
            _store.close()
        except Exception as exc:
            # Neo4j not configured — no-op
            log.debug("Neo4j store close failed (swallowed): %s", exc)
        _store = None


# ── Compatibility wrappers ───────────────────────────────────────────────
#
# These preserve the ``_load() -> (KnowledgeGraph, Path)`` and
# ``_save(graph, path)`` calling convention used by 40+ tool functions.
# They route through the Neo4jStore so no JSON files are involved.

_COMPAT_PATH = Path("/dev/null")  # placeholder, never used for I/O


def _load():
    """Load the graph from Neo4j. Returns ``(KnowledgeGraph, Path)`` for compat."""
    store = get_store()
    graph = store.load_graph()
    return graph, _COMPAT_PATH


def _save(graph, path=None) -> None:
    """Save the graph to Neo4j. ``path`` is ignored (compat placeholder)."""
    store = get_store()
    # Batch upsert all nodes and edges from the in-memory graph
    store.batch_upsert_nodes(list(graph.nodes.values()))
    store.batch_upsert_edges(list(graph.edges.values()))


def _kg_backend_name() -> str:
    """Always returns 'neo4j' (compat stub)."""
    return "neo4j"


def _json(data: Any) -> str:
    """Compact JSON serializer for tool return values."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@contextmanager
def graph_transaction():
    with _GRAPH_LOCK:
        graph, path = _load()
        yield graph
        _save(graph, path)
