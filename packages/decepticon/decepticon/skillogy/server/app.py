"""FastAPI REST app for Skillogy — Phase 1a, Neo4j-backed.

REST endpoints (graph-backed; the legacy in-memory dict registry is gone):

- ``GET  /v1/health``           — service liveness + skill_count + uptime
- ``POST /v1/skills:find``      — relationship-aware discovery
- ``POST /v1/skills:load``      — fetch one :Skill body + frontmatter
- ``POST /v1/skills:traverse``  — variable-length BFS from a Skill seed
- ``POST /v1/skills:moc``       — per-phase MoC summary
- ``GET  /openapi.json``        — generated OpenAPI 3.1 schema

The Phase 1a v0.2.1 service architecture pivot makes this app the single
holder of the Neo4j Bolt connection. ``RestSkillogyClient`` (and through
it ``SkillogyMiddleware``) consume the wire surface so the langgraph
agent image carries no Neo4j driver dependency.

The legacy ``/v1/skills:list`` + ``/v1/skills:ingest`` endpoints (and
the ``SkillRegistry`` + ``ingest_directory`` they depended on) are
removed. ``build_grpc_server`` is also gone: there are no
protoc-generated bindings, REST is the only supported transport, and
keeping a permanently-raising stub function alive only invited
accidental reintroduction.
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from typing import Any

from decepticon.skillogy.server.neo4j_backend import (
    CypherWriteRejected,
    Neo4jBackend,
)

log = logging.getLogger(__name__)


try:
    from pydantic import BaseModel
except ImportError:
    BaseModel = None  # type: ignore[assignment,misc]


if BaseModel is not None:

    class FindReq(BaseModel):
        query: str | None = None
        subdomain: str | None = None
        mitre_id: str | None = None
        tag: str | None = None
        tactic_id: str | None = None
        limit: int = 20
        # Per ADR-0008 — optional path-prefix allowlist enforced server-side
        # so the agent middleware's role context cannot be widened by a
        # tool-call argument. Unset / null preserves the unrestricted
        # behaviour for the standalone CLI, library use, and pytest.
        allowed_path_prefixes: list[str] | None = None

    class LoadReq(BaseModel):
        # Accept either a canonical /skills/.../SKILL.md path or a unique
        # frontmatter ``name``. The server resolves the name route via a
        # single-shot find before loading.
        name_or_path: str
        allowed_path_prefixes: list[str] | None = None  # ADR-0008

    class TraverseReq(BaseModel):
        from_path: str
        edge_types: list[str] | None = None
        depth: int = 2
        allowed_path_prefixes: list[str] | None = None  # ADR-0008

    class MocReq(BaseModel):
        phase: str
        limit: int = 25


def build_app(
    backend: Neo4jBackend,
    *,
    started_at: float | None = None,
    api_key: str | None = None,
):
    """Build the FastAPI app bound to ``backend``.

    ``api_key`` defaults to ``$SKILLOGY_API_KEY``; when unset, the
    protected endpoints are open. The ``GET /v1/health`` endpoint is
    always open so external orchestrators (compose, k8s) can probe
    without secret rotation.
    """
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Skillogy server requires FastAPI + Pydantic. Install with: "
            "pip install fastapi pydantic uvicorn"
        ) from exc

    _expected_key: str | None = (
        api_key if api_key is not None else os.environ.get("SKILLOGY_API_KEY")
    )

    async def _require_key(authorization: str | None = Header(default=None)) -> None:
        if _expected_key is None:
            return
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(token, _expected_key):
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    _protected = [Depends(_require_key)]

    app = FastAPI(
        title="Skillogy",
        version="0.2.0",
        description=(
            "Decepticon skill catalog service (Phase 1a, Neo4j-backed). "
            "Three relationship-aware operations plus a per-phase MoC "
            "summary; see /openapi.json for the wire schema."
        ),
    )
    boot_time = started_at or time.time()

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        try:
            stats = backend.health()
        except Exception as exc:  # noqa: BLE001
            log.warning("health check backend probe failed: %r", exc)
            return {
                "status": "degraded",
                "skill_count": 0,
                "uptime_seconds": int(time.time() - boot_time),
                "error": str(exc),
            }
        return {
            "status": stats.get("status", "ok"),
            "skill_count": stats.get("skill_count", 0),
            "uptime_seconds": int(time.time() - boot_time),
        }

    @app.post("/v1/skills:find", dependencies=_protected)
    async def find_skill(req: FindReq) -> dict[str, Any]:
        try:
            hits = backend.find_skill(
                query=req.query,
                subdomain=req.subdomain,
                mitre_id=req.mitre_id,
                tag=req.tag,
                tactic_id=req.tactic_id,
                limit=req.limit,
                allowed_path_prefixes=req.allowed_path_prefixes,
            )
        except ValueError as exc:
            # find_skill raises ValueError when no filters are passed —
            # surface it as a client-error code, not 500.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"count": len(hits), "hits": hits}

    @app.post("/v1/skills:load", dependencies=_protected)
    async def load_skill(req: LoadReq) -> dict[str, Any]:
        target = req.name_or_path
        allowed = req.allowed_path_prefixes
        if target.startswith("/skills/"):
            props = backend.load_skill(target, allowed_path_prefixes=allowed)
        else:
            # Resolve the name through find_skill so the same path-prefix
            # ACL guards the name → path lookup the agent sees (otherwise
            # a name match would leak the existence of skills outside the
            # allowlist via 404 vs success).
            try:
                hits = backend.find_skill(
                    query=target,
                    limit=10,
                    allowed_path_prefixes=allowed,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            exact = [h for h in hits if h.get("name") == target]
            if not exact:
                raise HTTPException(
                    status_code=404,
                    detail=f"no Skill with name or path matching {target!r}",
                )
            props = backend.load_skill(exact[0]["path"], allowed_path_prefixes=allowed)
        if props is None:
            raise HTTPException(status_code=404, detail=f"no Skill at path {target!r}")
        return {"props": props}

    @app.post("/v1/skills:traverse", dependencies=_protected)
    async def traverse(req: TraverseReq) -> dict[str, Any]:
        rows = backend.traverse(
            req.from_path,
            edge_types=req.edge_types,
            depth=req.depth,
            allowed_path_prefixes=req.allowed_path_prefixes,
        )
        return {"count": len(rows), "rows": rows}

    @app.post("/v1/skills:moc", dependencies=_protected)
    async def moc_summary(req: MocReq) -> dict[str, Any]:
        rows = backend.query_moc_summary(req.phase, limit=req.limit)
        return {"count": len(rows), "mocs": rows}

    # The amendment removes ``run_cypher_read`` from the agent surface,
    # but the backend method is kept for internal diagnostics. We expose
    # nothing here — the REST app is exactly the agent's three tools plus
    # health and MoC. The day a Phase 1b ``recall`` ships, this is the
    # one place to add a new endpoint.
    _ = CypherWriteRejected  # imported for downstream tests that probe symbols

    return app
