"""``python -m decepticon.skillogy`` — run the Skillogy server.

Phase 1a (Amendment v0.2.2) boot sequence:

1. Build a ``Neo4jBackend`` against the configured Bolt URI (waits for
   the graph to be reachable; the compose ``depends_on: neo4j (healthy)``
   gating means it should already be up).
2. Optionally ingest the CI-built ``skills.cypher`` dump into Neo4j so
   a fresh container boot ends up with the corpus loaded (idempotent —
   the builder emits only ``MERGE`` statements).
3. Start the FastAPI REST app on ``$SKILLOGY_REST_PORT``.

Environment variables:
  SKILLOGY_REST_PORT          (default 9100)
  SKILLOGY_NEO4J_URI          (default ``bolt://neo4j:7687``)
  SKILLOGY_NEO4J_USER         (default ``neo4j``)
  SKILLOGY_NEO4J_PASSWORD     (default ``decepticon-graph``)
  SKILLOGY_CYPHER_PATH        (default ``/app/skills.cypher`` — baked into the image)
  SKILLOGY_AUTO_INGEST        (default ``1``; set ``0`` to skip the bulk load)
  SKILLOGY_API_KEY            (optional Bearer-token auth for the protected endpoints)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from decepticon.skillogy.server.app import build_app
from decepticon.skillogy.server.neo4j_backend import Neo4jBackend

log = logging.getLogger("skillogy")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # The Neo4j driver logs every cartesian-product hint at INFO during
    # bulk ingest — thousands of edge MERGEs against AssetType etc. trip
    # this. It's expected (the MERGE intentionally joins disconnected
    # nodes); silencing the notification logger keeps boot logs readable.
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)


def _build_backend() -> Neo4jBackend:
    return Neo4jBackend(
        uri=os.environ.get("SKILLOGY_NEO4J_URI", "bolt://neo4j:7687"),
        user=os.environ.get("SKILLOGY_NEO4J_USER", "neo4j"),
        password=os.environ.get("SKILLOGY_NEO4J_PASSWORD", "decepticon-graph"),
    )


def _maybe_ingest(backend: Neo4jBackend) -> None:
    if os.environ.get("SKILLOGY_AUTO_INGEST", "1").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        log.info("SKILLOGY_AUTO_INGEST disabled; skipping cypher load")
        return
    cypher_path = Path(os.environ.get("SKILLOGY_CYPHER_PATH", "/app/skills.cypher"))
    if not cypher_path.exists():
        log.warning(
            "skills.cypher not found at %s; serving an empty graph until "
            "the operator ingests something else",
            cypher_path,
        )
        return
    cypher_text = cypher_path.read_text(encoding="utf-8")
    n = backend.bulk_ingest_cypher(cypher_text)
    log.info("ingested %d Cypher statements from %s", n, cypher_path)

    # Hybrid retrieval (ADR-0011): once the corpus is loaded, create the
    # vector index and embed each skill through the litellm proxy. The dump
    # is deliberately embedding-free, so this is what makes semantic
    # find_skill possible. It degrades to a no-op when the proxy env is
    # absent — the substring path keeps working either way.
    from decepticon.skillogy.embed_ingest import ingest_embeddings  # noqa: PLC0415

    ingest_embeddings(backend)


def _start_rest(backend: Neo4jBackend, port: int, started_at: float) -> None:
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Skillogy REST requires uvicorn. Install with: pip install uvicorn"
        ) from exc
    app = build_app(backend, started_at=started_at)
    # 0.0.0.0 is intentional: the Skillogy container is only exposed on
    # decepticon-net; docker-compose pins the host port to 127.0.0.1.
    config = uvicorn.Config(  # nosec B104
        app=app, host="0.0.0.0", port=port, log_level="info"
    )
    uvicorn.Server(config).run()


def _ingest_in_background(backend: Neo4jBackend) -> None:
    """Run the boot-time cypher ingest off the main thread.

    On a cold container the bundled ``skills.cypher`` is ~3.7 MB and
    Neo4j MERGEs ~6000 statements over the bolt driver — that takes
    several minutes on the first boot. Running it on the main thread
    blocks ``uvicorn.run()`` from binding the listener until the
    ingest finishes, which leaves ``/v1/health`` unreachable and
    Docker's healthcheck flapping past ``start_period``. We move the
    ingest to a daemon thread so the REST server comes up first and
    the healthcheck passes immediately; the corpus then loads in the
    background and the existing ``skill_count`` field in
    ``/v1/health`` reports its progress.
    """
    try:
        _maybe_ingest(backend)
    except Exception as exc:  # noqa: BLE001
        # Failing to ingest is loud but not fatal — the operator may
        # be running against a Neo4j that was pre-loaded out of band
        # (a different cypher file, or a manual seed). REST stays up
        # so health probes can report the situation.
        log.error("cypher ingest failed: %r — continuing without it", exc)


def main() -> int:
    _setup_logging()
    rest_port = int(os.environ.get("SKILLOGY_REST_PORT", "9100"))

    backend = _build_backend()
    started_at = time.time()

    # Start the bulk cypher ingest off the main thread before serving so
    # the REST listener comes up immediately. See ``_ingest_in_background``
    # for the rationale. The thread is a daemon so a SIGTERM during ingest
    # tears it down with the process.
    ingest_thread = threading.Thread(
        target=_ingest_in_background,
        args=(backend,),
        name="skillogy-ingest",
        daemon=True,
    )
    ingest_thread.start()

    def _handle_term(_signum, _frame):
        log.info("SIGTERM received; closing backend and exiting")
        try:
            backend.close()
        finally:
            sys.exit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_term)

    _start_rest(backend, rest_port, started_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
