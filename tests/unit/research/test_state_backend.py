"""Tests for Neo4j-only research state management."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research.graph import KnowledgeGraph, Node, NodeKind


class _FakeStore:
    """In-memory fake Neo4j store for unit tests."""

    def __init__(self) -> None:
        self.graph = KnowledgeGraph()
        self.load_calls = 0
        self.save_calls = 0
        self.schema_ensured = False
        self.closed = False

    def load_graph(self):
        self.load_calls += 1
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes):
        for n in nodes:
            self.graph.upsert_node(n)
        self.save_calls += 1
        return len(nodes)

    def batch_upsert_edges(self, edges):
        for e in edges:
            self.graph.upsert_edge(e)
        return len(edges)

    def ensure_schema(self):
        self.schema_ensured = True

    def close(self):
        self.closed = True

    def revision(self):
        return 0.0

    def stats(self):
        return self.graph.stats()


@pytest.fixture(autouse=True)
def _clean_state() -> Generator[None, None, None]:
    state._store = None
    yield
    state._store = None


def test_get_store_returns_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    assert state.get_store() is fake


def test_close_store_clears_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    state.close_store()
    assert state._store is None
    assert fake.closed


def test_load_compat_returns_graph_and_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    graph, path = state._load()
    assert isinstance(graph, KnowledgeGraph)
    assert fake.load_calls == 1


def test_save_compat_batch_upserts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    graph = KnowledgeGraph()
    graph.upsert_node(Node.make(NodeKind.HOST, "10.0.0.1", key="host::10.0.0.1"))
    state._save(graph, None)
    assert fake.save_calls == 1
    assert fake.graph.stats()["nodes"] == 1


def test_json_helper() -> None:
    result = state._json({"key": "value"})
    assert '"key": "value"' in result
