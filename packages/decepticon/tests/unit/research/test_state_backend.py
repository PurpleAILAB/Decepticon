"""Tests for Neo4j-only research state management."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from decepticon.tools.research import _state as state
from decepticon_core.types.kg import KnowledgeGraph, Node, NodeKind


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


def test_transaction_does_not_save_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_calls: list[KnowledgeGraph] = []

    monkeypatch.setattr(state, "_load", lambda: (KnowledgeGraph(), Path("/dev/null")))
    monkeypatch.setattr(state, "_save", lambda graph, path=None: save_calls.append(graph))

    with pytest.raises(RuntimeError):
        with state.graph_transaction():
            raise RuntimeError("boom")

    assert save_calls == []


def test_transaction_saves_once_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_calls: list[KnowledgeGraph] = []

    monkeypatch.setattr(state, "_load", lambda: (KnowledgeGraph(), Path("/dev/null")))
    monkeypatch.setattr(state, "_save", lambda graph, path=None: save_calls.append(graph))

    with state.graph_transaction() as g:
        g.upsert_node(Node.make(NodeKind.HOST, "10.0.0.2", key="host::10.0.0.2"))

    assert len(save_calls) == 1


def test_kg_degrades_returns_graceful_message_when_store_unavailable() -> None:
    """kg_* tools must degrade (not raise) when Neo4j is unconfigured.

    Agents such as osint_operator import the kg_* tools directly (bypassing
    the KG middleware slot's guard), so a call would otherwise surface the
    ``KGStoreConfigError`` from ``get_store()`` as a hard tool error. The
    ``kg_degrades`` wrapper converts it into a message the agent can act on.
    """
    import json

    from decepticon.middleware.kg_internal.store import KGStoreConfigError

    @state.kg_degrades
    def raises() -> str:
        raise KGStoreConfigError("KGStore missing required env vars: DECEPTICON_NEO4J_URI")

    out = json.loads(raises())
    assert out["error"] == "knowledge_graph_unavailable"
    assert "DECEPTICON_NEO4J_URI" in out["detail"]

    @state.kg_degrades
    def ok() -> str:
        return '{"id": "n1"}'

    assert ok() == '{"id": "n1"}'
