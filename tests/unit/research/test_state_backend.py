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


class TestSeedingToggle:
    def test_seeding_on_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DECEPTICON_KG_SEED", raising=False)
        assert state._seeding_enabled() is True

    def test_seeding_off_when_explicitly_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("0", "false", "no", "off"):
            monkeypatch.setenv("DECEPTICON_KG_SEED", val)
            assert state._seeding_enabled() is False

    def test_seeding_on_for_truthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_KG_SEED", "1")
        assert state._seeding_enabled() is True


def test_get_store_seeds_reference_data(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state.Neo4jStore, "from_env", classmethod(lambda cls: fake))
    monkeypatch.delenv("DECEPTICON_KG_SEED", raising=False)
    store = state.get_store()
    assert store is fake
    assert fake.schema_ensured
    stats = fake.graph.stats()
    assert stats.get("node.Technique", 0) > 300
    assert stats.get("node.Skill", 0) > 0


def test_get_store_skips_seeding_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state.Neo4jStore, "from_env", classmethod(lambda cls: fake))
    monkeypatch.setenv("DECEPTICON_KG_SEED", "0")
    state.get_store()
    assert fake.graph.stats()["nodes"] == 0


def test_get_store_survives_seeding_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A seeding error must not break store initialization."""
    fake = _FakeStore()

    def _boom(_nodes: list) -> int:
        raise RuntimeError("seed blew up")

    fake.batch_upsert_nodes = _boom  # type: ignore[method-assign]
    monkeypatch.setattr(state.Neo4jStore, "from_env", classmethod(lambda cls: fake))
    monkeypatch.delenv("DECEPTICON_KG_SEED", raising=False)
    store = state.get_store()
    assert store is fake  # initialization succeeded despite the seeding failure
