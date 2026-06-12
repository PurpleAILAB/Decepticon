"""Tests for the Phase 1a Neo4j-backed REST app (``decepticon.skillogy.server.app``).

Each endpoint is exercised against a fake ``Neo4jBackend`` so the
FastAPI surface is pinned without needing a live Neo4j during the unit
lane. The live dogfood (``make dev`` + container smoke) is the
complementary integration check; this file pins shapes, error codes,
and auth gating.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from decepticon.skillogy.server.app import build_app


class _FakeBackend:
    """Stand-in for ``Neo4jBackend`` shaped exactly like the four methods
    ``build_app`` calls — health, find_skill, load_skill, traverse,
    query_moc_summary. Each canned response can be overridden per test.
    """

    def __init__(
        self,
        *,
        health_response: dict[str, Any] | None = None,
        health_exc: Exception | None = None,
        find_response: list[dict] | None = None,
        find_exc: Exception | None = None,
        load_response: dict | None = None,
        traverse_response: list[dict] | None = None,
        moc_response: list[dict] | None = None,
    ) -> None:
        self._health_response = health_response or {"status": "ok", "skill_count": 42}
        self._health_exc = health_exc
        self._find_response = find_response if find_response is not None else []
        self._find_exc = find_exc
        self._load_response = load_response
        self._traverse_response = traverse_response if traverse_response is not None else []
        self._moc_response = moc_response if moc_response is not None else []
        self.find_calls: list[dict] = []
        self.load_calls: list[str] = []
        self.traverse_calls: list[dict] = []
        self.moc_calls: list[str] = []

    def health(self) -> dict[str, Any]:
        if self._health_exc is not None:
            raise self._health_exc
        return self._health_response

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
    ) -> list[dict]:
        self.find_calls.append(
            {
                "query": query,
                "subdomain": subdomain,
                "mitre_id": mitre_id,
                "tag": tag,
                "tactic_id": tactic_id,
                "limit": limit,
                "allowed_path_prefixes": allowed_path_prefixes,
            }
        )
        if self._find_exc is not None:
            raise self._find_exc
        return self._find_response

    def load_skill(
        self,
        path: str,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> dict | None:
        self.load_calls.append(path)
        return self._load_response

    def traverse(
        self,
        from_path: str,
        edge_types: list[str] | None = None,
        depth: int = 2,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> list[dict]:
        self.traverse_calls.append(
            {
                "from_path": from_path,
                "edge_types": edge_types,
                "depth": depth,
                "allowed_path_prefixes": allowed_path_prefixes,
            }
        )
        return self._traverse_response

    def query_moc_summary(self, phase: str, *, limit: int = 25) -> list[dict]:
        self.moc_calls.append(phase)
        return self._moc_response


# ── health ─────────────────────────────────────────────────────────────


class TestHealth:
    def test_ok_response(self) -> None:
        backend = _FakeBackend(health_response={"status": "ok", "skill_count": 269})
        with TestClient(build_app(backend)) as client:
            r = client.get("/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["skill_count"] == 269
        assert isinstance(body["uptime_seconds"], int)

    def test_backend_exception_yields_degraded_not_500(self) -> None:
        # health must never 500 — orchestrators treat that as crash-loop.
        backend = _FakeBackend(health_exc=RuntimeError("driver down"))
        with TestClient(build_app(backend)) as client:
            r = client.get("/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert "driver down" in body["error"]


# ── find ───────────────────────────────────────────────────────────────


class TestFind:
    def test_filters_threaded_through(self) -> None:
        backend = _FakeBackend(
            find_response=[
                {
                    "name": "kerberoasting",
                    "path": "/skills/standard/ad/kerberoasting/SKILL.md",
                    "subdomain": "active-directory",
                    "description": "...",
                    "matched_mitre": ["T1558.003"],
                    "matched_tags": ["kerberoasting"],
                }
            ]
        )
        with TestClient(build_app(backend)) as client:
            r = client.post(
                "/v1/skills:find",
                json={
                    "subdomain": "active-directory",
                    "tag": "kerberoasting",
                    "limit": 5,
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["hits"][0]["name"] == "kerberoasting"
        assert backend.find_calls == [
            {
                "query": None,
                "subdomain": "active-directory",
                "mitre_id": None,
                "tag": "kerberoasting",
                "tactic_id": None,
                "limit": 5,
                # ADR-0008 — request body omits ``allowed_path_prefixes``
                # for the standalone CLI path, so the backend sees ``None``.
                "allowed_path_prefixes": None,
            }
        ]

    def test_no_filter_is_400_not_500(self) -> None:
        backend = _FakeBackend(find_exc=ValueError("requires at least one of: ..."))
        with TestClient(build_app(backend)) as client:
            r = client.post("/v1/skills:find", json={})
        assert r.status_code == 400
        body = r.json()
        assert "requires at least one of" in body["detail"]


# ── load ───────────────────────────────────────────────────────────────


class TestLoad:
    def test_path_route(self) -> None:
        backend = _FakeBackend(
            load_response={
                "name": "x",
                "path": "/skills/x/SKILL.md",
                "body": "BODY",
            }
        )
        with TestClient(build_app(backend)) as client:
            r = client.post(
                "/v1/skills:load",
                json={"name_or_path": "/skills/x/SKILL.md"},
            )
        assert r.status_code == 200
        assert r.json()["props"]["name"] == "x"
        assert backend.load_calls == ["/skills/x/SKILL.md"]

    def test_name_route_loads_directly_without_find(self) -> None:
        backend = _FakeBackend(
            load_response={
                "name": "kerberoasting",
                "path": "/skills/ad/k/SKILL.md",
                "body": "...",
            },
        )
        with TestClient(build_app(backend)) as client:
            r = client.post("/v1/skills:load", json={"name_or_path": "kerberoasting"})
        assert r.status_code == 200
        # The server passes a bare name straight to backend.load_skill —
        # never through find_skill, whose keyword ranking the mixed APT+web
        # corpus pollutes (a name outside find's top-N would 404).
        assert backend.find_calls == []
        assert backend.load_calls == ["kerberoasting"]

    def test_name_no_exact_match_is_404(self) -> None:
        # load_response=None — backend.load_skill resolves neither a path
        # nor an exact name (near-misses like "kerberoasting-blind" don't
        # count; only exact matches resolve).
        backend = _FakeBackend()
        with TestClient(build_app(backend)) as client:
            r = client.post("/v1/skills:load", json={"name_or_path": "kerberoasting"})
        assert r.status_code == 404
        assert "no Skill with name or path matching" in r.json()["detail"]

    def test_path_not_found_is_404(self) -> None:
        backend = _FakeBackend(load_response=None)
        with TestClient(build_app(backend)) as client:
            r = client.post(
                "/v1/skills:load",
                json={"name_or_path": "/skills/missing/SKILL.md"},
            )
        assert r.status_code == 404


# ── traverse ───────────────────────────────────────────────────────────


class TestTraverse:
    def test_payload_threaded_through(self) -> None:
        backend = _FakeBackend(
            traverse_response=[
                {
                    "labels": ["Skill"],
                    "key": "neighbor",
                    "depth": 1,
                    "edge_chain": ["IN_PHASE"],
                }
            ]
        )
        with TestClient(build_app(backend)) as client:
            r = client.post(
                "/v1/skills:traverse",
                json={
                    "from_path": "/skills/x/SKILL.md",
                    "edge_types": ["IN_PHASE"],
                    "depth": 3,
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert backend.traverse_calls == [
            {
                "from_path": "/skills/x/SKILL.md",
                "edge_types": ["IN_PHASE"],
                "depth": 3,
                # ADR-0008 — request body omits ``allowed_path_prefixes``,
                # so the backend sees ``None``.
                "allowed_path_prefixes": None,
            }
        ]


# ── moc summary ────────────────────────────────────────────────────────


class TestMoc:
    def test_phase_request_returns_bullets(self) -> None:
        backend = _FakeBackend(
            moc_response=[
                {"name": "passive-recon", "description": "OSINT", "parent_phase": "reconnaissance"},
                {
                    "name": "active-recon",
                    "description": "scanning",
                    "parent_phase": "reconnaissance",
                },
            ]
        )
        with TestClient(build_app(backend)) as client:
            r = client.post("/v1/skills:moc", json={"phase": "reconnaissance"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert {m["name"] for m in body["mocs"]} == {"passive-recon", "active-recon"}
        assert backend.moc_calls == ["reconnaissance"]

    def test_empty_phase_yields_empty_list(self) -> None:
        backend = _FakeBackend(moc_response=[])
        with TestClient(build_app(backend)) as client:
            r = client.post("/v1/skills:moc", json={"phase": "wireless"})
        assert r.status_code == 200
        body = r.json()
        assert body == {"count": 0, "mocs": []}


# ── auth gating ────────────────────────────────────────────────────────


class TestAuth:
    def test_protected_endpoints_require_bearer_when_key_set(self) -> None:
        backend = _FakeBackend()
        app = build_app(backend, api_key="secret-token")
        with TestClient(app) as client:
            # No Authorization header — must be 401.
            r = client.post("/v1/skills:find", json={"query": "x"})
            assert r.status_code == 401

            # Wrong token — must be 401.
            r = client.post(
                "/v1/skills:find",
                json={"query": "x"},
                headers={"Authorization": "Bearer nope"},
            )
            assert r.status_code == 401

            # Correct token — must be 200.
            r = client.post(
                "/v1/skills:find",
                json={"query": "x"},
                headers={"Authorization": "Bearer secret-token"},
            )
            assert r.status_code == 200

    def test_health_endpoint_is_always_open(self) -> None:
        backend = _FakeBackend()
        app = build_app(backend, api_key="secret-token")
        with TestClient(app) as client:
            r = client.get("/v1/health")
            assert r.status_code == 200, "health must stay open for orchestrators"

    def test_no_key_means_all_endpoints_open(self) -> None:
        backend = _FakeBackend(find_response=[])
        app = build_app(backend, api_key=None)
        with TestClient(app) as client:
            r = client.post("/v1/skills:find", json={"query": "x"})
            assert r.status_code == 200


# ── removed endpoints stay removed ─────────────────────────────────────


@pytest.mark.parametrize("path", ["/v1/skills:list", "/v1/skills:ingest"])
def test_legacy_endpoints_404(path: str) -> None:
    """The in-memory list/ingest endpoints were dropped — make sure a
    silent reintroduction is caught by CI."""
    backend = _FakeBackend()
    with TestClient(build_app(backend)) as client:
        r = client.post(path, json={})
    assert r.status_code == 404
