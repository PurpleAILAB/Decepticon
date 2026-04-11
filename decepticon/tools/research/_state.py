"""Shared Knowledge Graph state helpers.

This module centralises persistence for the research graph so all tool modules
(``tools.py``, ``scanner_tools.py``, ``patch.py``) share the same load/save
behavior and cache policy.

Backends:
- ``json``  (default): ``/workspace/kg.json``
- ``neo4j`` (optional): configured via ``DECEPTICON_NEO4J_*`` env vars
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.tools.research.graph import DEFAULT_PATH, KnowledgeGraph, load_graph, save_graph
from decepticon.tools.research.neo4j_store import Neo4jStore

log = get_logger("research.state")

_VALID_BACKENDS = {"json", "neo4j"}


def _kg_backend_name() -> str:
    raw = os.environ.get("DECEPTICON_KG_BACKEND", "json").strip().lower()
    if raw in _VALID_BACKENDS:
        return raw
    log.warning(
        "Unknown DECEPTICON_KG_BACKEND; falling back to json",
        extra={"backend": raw},
    )
    return "json"


def _kg_path() -> Path:
    """Resolve the JSON graph path (also used as cache key for neo4j backend)."""
    return Path(os.environ.get("DECEPTICON_KG_PATH", str(DEFAULT_PATH)))


# ── KG load cache ──────────────────────────────────────────────────────
# Cache key includes backend + path so switching backends does not leak
# stale values.
_kg_cache: dict[tuple[str, Path], tuple[float, KnowledgeGraph]] = {}
_neo4j_store: Neo4jStore | None = None


def _cache_key(backend: str, path: Path) -> tuple[str, Path]:
    return backend, path


def _get_neo4j_store() -> Neo4jStore:
    global _neo4j_store
    if _neo4j_store is None:
        _neo4j_store = Neo4jStore.from_env()
    return _neo4j_store


def _load_json(path: Path) -> tuple[KnowledgeGraph, Path]:
    key = _cache_key("json", path)
    try:
        mtime = path.stat().st_mtime if path.exists() else -1.0
    except OSError:
        mtime = -1.0

    entry = _kg_cache.get(key)
    if entry is not None and entry[0] == mtime:
        return entry[1], path

    graph = load_graph(path)
    _kg_cache[key] = (mtime, graph)
    return graph, path


def _load_neo4j(path: Path) -> tuple[KnowledgeGraph, Path]:
    store = _get_neo4j_store()
    key = _cache_key("neo4j", path)
    revision = store.revision()

    entry = _kg_cache.get(key)
    if entry is not None and entry[0] == revision:
        return entry[1], path

    graph = store.load_graph()
    _kg_cache[key] = (revision, graph)
    return graph, path


def _load() -> tuple[KnowledgeGraph, Path]:
    backend = _kg_backend_name()
    path = _kg_path()
    if backend == "neo4j":
        try:
            return _load_neo4j(path)
        except Exception as exc:
            log.warning(
                "Neo4j backend unavailable; falling back to JSON persistence",
                extra={"error": str(exc)},
            )
    return _load_json(path)


def _save(graph: KnowledgeGraph, path: Path) -> None:
    backend = _kg_backend_name()

    if backend == "neo4j":
        try:
            store = _get_neo4j_store()
            store.save_graph(graph)
            revision = store.revision()
            _kg_cache[_cache_key("neo4j", path)] = (revision, graph)
            return
        except Exception as exc:
            log.warning(
                "Neo4j backend unavailable; persisting to JSON fallback",
                extra={"error": str(exc)},
            )

    save_graph(graph, path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    _kg_cache[_cache_key("json", path)] = (mtime, graph)


def _invalidate_kg_cache() -> None:
    """Drop persistence cache (tests) and close optional neo4j driver."""
    global _neo4j_store
    _kg_cache.clear()
    if _neo4j_store is not None:
        try:
            _neo4j_store.close()
        except Exception:
            pass
    _neo4j_store = None


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)
