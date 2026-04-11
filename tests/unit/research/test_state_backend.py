"""Tests for research state backend selection (json vs neo4j)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from decepticon.research import _state as state
from decepticon.tools.research.graph import KnowledgeGraph, Node, NodeKind


class _FakeNeo4jStore:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()
        self.rev = 0.0
        self.load_calls = 0
        self.save_calls = 0
        self.closed = False

    def revision(self) -> float:
        return self.rev

    def load_graph(self):
        self.load_calls += 1
        return self.graph.model_copy(deep=True)

    def save_graph(self, graph):
        self.save_calls += 1
        self.graph = graph.model_copy(deep=True)
        self.rev += 1.0

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _clean_state_cache() -> Generator[None, None, None]:
    state._invalidate_kg_cache()
    yield
    state._invalidate_kg_cache()


def test_unknown_backend_falls_back_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECEPTICON_KG_BACKEND", "something-else")
    assert state._kg_backend_name() == "json"


def test_json_backend_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    kg_path = tmp_path / "kg.json"
    monkeypatch.setenv("DECEPTICON_KG_BACKEND", "json")
    monkeypatch.setenv("DECEPTICON_KG_PATH", str(kg_path))

    graph, path = state._load()
    assert path == kg_path
    assert graph.stats()["nodes"] == 0

    graph.upsert_node(Node.make(NodeKind.HOST, "10.0.0.7", key="host::10.0.0.7"))
    state._save(graph, path)

    loaded, _ = state._load()
    assert loaded.stats()["nodes"] == 1


def test_neo4j_backend_uses_store_and_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_store = _FakeNeo4jStore()

    monkeypatch.setenv("DECEPTICON_KG_BACKEND", "neo4j")
    monkeypatch.setenv("DECEPTICON_KG_PATH", str(tmp_path / "kg.json"))
    monkeypatch.setattr(state, "_get_neo4j_store", lambda: fake_store)

    graph, path = state._load()
    assert path.name == "kg.json"
    assert fake_store.load_calls == 1

    # Cached: no revision change, so no additional DB read.
    _cached, _ = state._load()
    assert fake_store.load_calls == 1

    graph.upsert_node(Node.make(NodeKind.URL, "https://target.local", key="url::target"))
    state._save(graph, path)
    assert fake_store.save_calls == 1

    # Save refreshes cache to the new revision; no extra read needed.
    reloaded, _ = state._load()
    assert reloaded.stats()["nodes"] == 1
    assert fake_store.load_calls == 1
