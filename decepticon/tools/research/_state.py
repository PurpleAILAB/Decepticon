"""Neo4j-only state management for the attack graph.

Provides a singleton Neo4jStore and convenience functions for
tool modules to access it.
"""

from __future__ import annotations

import json
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.tools.research.neo4j_store import Neo4jStore

log = get_logger("research.state")

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
        except Exception:
            pass
        _store = None


def _json(data: Any) -> str:
    """Compact JSON serializer for tool return values."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)
