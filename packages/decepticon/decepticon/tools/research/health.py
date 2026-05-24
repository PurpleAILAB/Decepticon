"""Knowledge-graph backend health diagnostics."""

from __future__ import annotations

import json
import os
from typing import Any

from decepticon.tools.research import _state


def backend_health() -> dict[str, Any]:
    """Return backend health and startup diagnostics."""
    payload: dict[str, Any] = {
        "backend": "neo4j",
        "ok": True,
    }

    payload["neo4j"] = {
        "uri": os.environ.get("DECEPTICON_NEO4J_URI", ""),
        "user": os.environ.get("DECEPTICON_NEO4J_USER", ""),
        "database": os.environ.get("DECEPTICON_NEO4J_DATABASE", "neo4j"),
    }

    try:
        store = _state.get_store()
        revision = store.revision()
        stats = store.stats()
        payload["revision"] = revision
        payload["stats"] = stats
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
