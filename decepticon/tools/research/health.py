"""Knowledge-graph backend health diagnostics."""

from __future__ import annotations

import json
import os
from typing import Any

from decepticon.research import _state


def backend_health() -> dict[str, Any]:
    """Return backend health and startup diagnostics."""
    backend = _state._kg_backend_name()
    kg_path = _state._kg_path()

    payload: dict[str, Any] = {
        "backend": backend,
        "path": str(kg_path),
        "ok": True,
    }

    if backend == "json":
        payload["exists"] = kg_path.exists()
        payload["parent_exists"] = kg_path.parent.exists()
        try:
            graph, _ = _state._load()
            payload["stats"] = graph.stats()
        except Exception as exc:  # pragma: no cover - defensive
            payload["ok"] = False
            payload["error"] = str(exc)
        return payload

    # Neo4j mode diagnostics
    payload["neo4j"] = {
        "uri": os.environ.get("DECEPTICON_NEO4J_URI", ""),
        "user": os.environ.get("DECEPTICON_NEO4J_USER", ""),
        "database": os.environ.get("DECEPTICON_NEO4J_DATABASE", "neo4j"),
    }

    try:
        store = _state._get_neo4j_store()
        revision = store.revision()
        graph = store.load_graph()
        payload["revision"] = revision
        payload["stats"] = graph.stats()
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = str(exc)

    return payload


def main() -> None:
    """CLI entrypoint for runtime diagnostics.

    Exit code is 0 when healthy, 1 otherwise.
    """
    report = backend_health()
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    raise SystemExit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()
