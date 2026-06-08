"""REST client for the Phase 1a Skillogy service (Amendment v0.2.2).

Mirrors the ``Neo4jBackend`` surface exactly — same method names, same
keyword signatures, same return shapes — so ``SkillogyMiddleware``'s
tool wrappers don't care whether they're talking to a local backend
(unit tests) or the standalone container (production). The middleware
holds one instance per agent process.

httpx-based, **synchronous**. The tool wrappers (``find_skill``,
``load_skill``, ``traverse``) are themselves sync ``@tool`` closures
and the per-phase MoC summary is rendered once at middleware boot, so
there is no reason to pay the async overhead.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


class SkillogyClientError(RuntimeError):
    """Raised on transport failures or non-2xx responses from the server."""


class RestSkillogyClient:
    """Thin sync REST client. Drop-in replacement for ``Neo4jBackend``.

    The wire surface matches ``server/app.py``'s five endpoints:

      GET  /v1/health             → ``health()``
      POST /v1/skills:find        → ``find_skill(...)``
      POST /v1/skills:load        → ``load_skill(path)``
      POST /v1/skills:traverse    → ``traverse(...)``
      POST /v1/skills:moc         → ``query_moc_summary(...)``

    Reuses a single ``httpx.Client`` for the process lifetime so the
    connection pool stays warm across the agent's many sequential
    lookups.
    """

    def __init__(
        self,
        base_url: str = "http://skillogy:9100",
        *,
        timeout: float = 10.0,
        api_key: str | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client: Any = None

    # ---- transport ----------------------------------------------------

    def _http(self):
        if self._client is None:
            try:
                import httpx  # noqa: PLC0415
            except ImportError as exc:
                raise SkillogyClientError("httpx not installed") from exc
            self._client = httpx.Client(timeout=self._timeout, headers=self._headers)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def _post(self, path: str, payload: dict) -> dict[str, Any]:
        resp = self._http().post(f"{self._base}{path}", json=payload)
        if resp.status_code == 404:
            return {"_status": 404, "detail": resp.json().get("detail", "")}
        if resp.status_code >= 400:
            raise SkillogyClientError(
                f"POST {path} returned HTTP {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json()

    def _get(self, path: str) -> dict[str, Any]:
        resp = self._http().get(f"{self._base}{path}")
        if resp.status_code >= 400:
            raise SkillogyClientError(
                f"GET {path} returned HTTP {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json()

    # ---- mirrored surface (matches Neo4jBackend) ----------------------

    def health(self) -> dict[str, Any]:
        return self._get("/v1/health")

    def find_skill(
        self,
        *,
        query: str | None = None,
        subdomain: str | None = None,
        mitre_id: str | None = None,
        tag: str | None = None,
        tactic_id: str | None = None,
        limit: int = 20,
        allowed_path_prefixes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"limit": limit}
        if query is not None:
            payload["query"] = query
        if subdomain is not None:
            payload["subdomain"] = subdomain
        if mitre_id is not None:
            payload["mitre_id"] = mitre_id
        if tag is not None:
            payload["tag"] = tag
        if tactic_id is not None:
            payload["tactic_id"] = tactic_id
        # ADR-0008: per-role path-prefix ACL. Sent only when populated so
        # the unrestricted CLI / library path keeps using the existing
        # request shape.
        if allowed_path_prefixes:
            payload["allowed_path_prefixes"] = list(allowed_path_prefixes)
        try:
            data = self._post("/v1/skills:find", payload)
        except SkillogyClientError as exc:
            # The 400 "requires at least one of: ..." case maps cleanly
            # to ValueError so the tool wrappers' existing surfacing
            # logic does the right thing.
            if "HTTP 400" in str(exc):
                raise ValueError(str(exc)) from exc
            raise
        return list(data.get("hits") or [])

    def load_skill(
        self,
        path: str,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"name_or_path": path}
        if allowed_path_prefixes:
            payload["allowed_path_prefixes"] = list(allowed_path_prefixes)
        data = self._post("/v1/skills:load", payload)
        if data.get("_status") == 404:
            return None
        return dict(data.get("props") or {})

    def traverse(
        self,
        from_path: str,
        edge_types: list[str] | None = None,
        depth: int = 2,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"from_path": from_path, "depth": depth}
        if edge_types is not None:
            payload["edge_types"] = edge_types
        if allowed_path_prefixes:
            payload["allowed_path_prefixes"] = list(allowed_path_prefixes)
        data = self._post("/v1/skills:traverse", payload)
        return list(data.get("rows") or [])

    def query_moc_summary(self, phase: str, *, limit: int = 25) -> list[dict[str, Any]]:
        data = self._post("/v1/skills:moc", {"phase": phase, "limit": limit})
        return list(data.get("mocs") or [])


# ── factory helper used by SkillogyMiddleware ─────────────────────────


def from_env() -> RestSkillogyClient:
    """Build a client from ``DECEPTICON_SKILLOGY_URL`` + optional bearer.

    Defaults to ``http://skillogy:9100`` (the compose hostname). The
    middleware calls this when no explicit client is injected.
    """
    return RestSkillogyClient(
        base_url=os.environ.get("DECEPTICON_SKILLOGY_URL", "http://skillogy:9100"),
        api_key=os.environ.get("DECEPTICON_SKILLOGY_API_KEY") or None,
    )
