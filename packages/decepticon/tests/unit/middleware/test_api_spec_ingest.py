from __future__ import annotations

from pathlib import Path
from typing import Any

from decepticon.middleware.kg_internal.ingest import _adapt_api_spec, available_scanners


class _StubStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record_observations(
        self,
        observations: list[dict[str, Any]],
        *,
        engagement: str,
        created_by: str,
        source_episode_id: str,
    ) -> dict[str, int]:
        self.calls.append(
            {
                "observations": observations,
                "engagement": engagement,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            }
        )
        return {"created": len(observations), "merged": 0, "edges": len(observations) - 1}


def test_api_spec_adapter_imports_openapi_without_requesting_target(tmp_path: Path) -> None:
    spec = tmp_path / "openapi.yaml"
    spec.write_text(
        """openapi: 3.0.0
servers:
  - url: https://api.example.test/v1
paths:
  /users:
    get:
      operationId: listUsers
      parameters:
        - name: limit
          in: query
    post:
      operationId: createUser
""",
        encoding="utf-8",
    )
    store = _StubStore()

    result = _adapt_api_spec(spec, store, "eng-1", "recon", "episode-1")  # type: ignore[arg-type]

    assert "api_spec" in available_scanners()
    assert result["source"] == "openapi"
    assert result["operations"] == 2
    assert len(store.calls) == 1
    call = store.calls[0]
    assert call["engagement"] == "eng-1"
    endpoints = [item for item in call["observations"] if item["kind"] == "Entrypoint"]
    assert {item["label"] for item in endpoints} == {"GET /users", "POST /users"}
    assert all(item["props"]["execution_state"] == "imported" for item in endpoints)
    assert all(item["props"]["requires_roe"] is True for item in endpoints)


def test_api_spec_adapter_imports_postman_collection(tmp_path: Path) -> None:
    collection = tmp_path / "collection.json"
    collection.write_text(
        """{
  "info": {"name": "test", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
  "item": [{"name": "health", "request": {"method": "GET", "url": "https://api.example.test/health"}}]
}""",
        encoding="utf-8",
    )
    store = _StubStore()

    result = _adapt_api_spec(collection, store, "eng-1", "recon", "episode-1")  # type: ignore[arg-type]

    assert result["source"] == "postman"
    assert result["operations"] == 1
    endpoint = next(item for item in store.calls[0]["observations"] if item["kind"] == "Entrypoint")
    assert endpoint["label"] == "GET /health"
    assert endpoint["props"]["base_url"] == "https://api.example.test/health"


def test_api_spec_adapter_rejects_external_references(tmp_path: Path) -> None:
    spec = tmp_path / "openapi.json"
    spec.write_text(
        '{"openapi":"3.0.0","paths":{"/users":{"$ref":"https://example.test/paths.json"}}}',
        encoding="utf-8",
    )
    store = _StubStore()

    result = _adapt_api_spec(spec, store, "eng-1", "recon", "episode-1")  # type: ignore[arg-type]

    assert "external $ref" in result["error"]
    assert store.calls == []
