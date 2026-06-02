from __future__ import annotations

import json
import types
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest

from decepticon.tools.research import _engagement_scope as _scope
from decepticon.tools.research._engagement_scope import (
    reset_active_engagement,
    set_active_engagement,
)
from decepticon.tools.research.neo4j_store import (
    _ALL_NODE_LABELS,
    Neo4jConfig,
    Neo4jStore,
    Neo4jUnavailableError,
    _decode_props,
    _edge_cost_expr,
    _encode_props,
    _label_for,
    _promoted_props,
)
from decepticon_core.types.kg import (
    SEVERITY_COST_MULTIPLIER,
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
)


@pytest.fixture(autouse=True)
def _reset_engagement() -> Generator[None, None, None]:
    token = _scope._active_engagement.set(None)
    try:
        yield
    finally:
        _scope._active_engagement.reset(token)


class _FakeRecord:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


def _fake_record(data: dict[str, Any]) -> _FakeRecord:
    return _FakeRecord(data)


class _FakeResult:
    def __init__(
        self, rows: list[dict[str, Any]], single_row: dict[str, Any] | None = None
    ) -> None:
        self._rows = [_FakeRecord(r) for r in rows]
        self._single = _FakeRecord(single_row) if single_row is not None else None

    def __iter__(self):
        return iter(self._rows)

    def single(self) -> _FakeRecord | None:
        return self._single


class _FakeSession:
    def __init__(self, results: list[_FakeResult] | None = None) -> None:
        self._results = list(results or [])
        self._result_index = 0
        self.runs: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, *args: Any, **kwargs: Any) -> _FakeResult:
        all_params: dict[str, Any] = {}
        if args:
            for a in args:
                if isinstance(a, dict):
                    all_params.update(a)
        all_params.update(kwargs)
        self.runs.append((query, all_params))
        if self._result_index < len(self._results):
            r = self._results[self._result_index]
            self._result_index += 1
            return r
        return _FakeResult([])

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _FakeDriver:
    def __init__(self, sessions: list[_FakeSession] | None = None) -> None:
        self._sessions = list(sessions or [])
        self._session_index = 0
        self.close_called = False

    def session(self, database: str = "neo4j") -> _FakeSession:
        if self._session_index < len(self._sessions):
            s = self._sessions[self._session_index]
            self._session_index += 1
            return s
        return _FakeSession()

    def close(self) -> None:
        self.close_called = True


def _make_store(driver: _FakeDriver, database: str = "neo4j") -> Neo4jStore:
    store: Neo4jStore = object.__new__(Neo4jStore)
    store._driver = driver  # type: ignore[attr-defined]
    store._database = database  # type: ignore[attr-defined]
    return store


class TestDecodeProps:
    def test_none_returns_empty_dict(self) -> None:
        assert _decode_props(None) == {}

    def test_dict_input_returns_copy(self) -> None:
        original = {"a": 1}
        result = _decode_props(original)
        assert result == {"a": 1}
        assert result is not original

    def test_valid_json_string_returns_parsed_dict(self) -> None:
        assert _decode_props('{"k": "v"}') == {"k": "v"}

    def test_empty_string_returns_empty_dict(self) -> None:
        assert _decode_props("") == {}

    def test_non_str_non_dict_returns_empty_dict(self) -> None:
        assert _decode_props(123) == {}  # type: ignore[arg-type]

    def test_malformed_json_returns_empty_dict(self) -> None:
        assert _decode_props("{bad") == {}

    def test_json_array_returns_empty_dict(self) -> None:
        assert _decode_props("[1, 2]") == {}


class TestEncodeProps:
    def test_round_trip_basic_dict(self) -> None:
        result = _encode_props({"a": 1, "b": "x"})
        assert isinstance(result, str)
        assert json.loads(result) == {"a": 1, "b": "x"}

    def test_non_ascii_preserved(self) -> None:
        result = _encode_props({"host": "naïve"})
        assert "naïve" in result

    def test_unserializable_value_stringified(self) -> None:
        result = _encode_props({"ts": {1, 2, 3}})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "ts" in parsed

    def test_encode_fallback_on_forced_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.research import neo4j_store as mod

        original_dumps = json.dumps

        def bad_dumps(*args: Any, **kwargs: Any) -> str:
            raise TypeError("forced")

        monkeypatch.setattr(mod.json, "dumps", bad_dumps)
        assert mod._encode_props({"x": 1}) == "{}"
        monkeypatch.setattr(mod.json, "dumps", original_dumps)


class TestPromotedProps:
    def test_whitelisted_scalars_promoted(self) -> None:
        result = _promoted_props({"severity": "high", "validated": True, "engagement": "acme"})
        assert result == {"severity": "high", "validated": True}

    def test_absent_keys_omitted_not_nulled(self) -> None:
        result = _promoted_props({"severity": "low"})
        assert result == {"severity": "low"}
        assert "validated" not in result

    def test_none_values_skipped(self) -> None:
        result = _promoted_props({"severity": None, "validated": False})
        assert result == {"validated": False}

    def test_dict_and_list_values_skipped(self) -> None:
        result = _promoted_props({"status": ["open"], "severity": {"x": 1}, "cracked": True})
        assert result == {"cracked": True}

    def test_non_whitelisted_keys_skipped(self) -> None:
        result = _promoted_props({"notes": "free text", "ip": "10.0.0.1"})
        assert result == {"ip": "10.0.0.1"}

    def test_numeric_scalars_promoted(self) -> None:
        result = _promoted_props({"version": 1, "product": "nginx"})
        assert result == {"version": 1, "product": "nginx"}


class TestLabelFor:
    def test_host_label(self) -> None:
        assert _label_for(NodeKind.HOST) == "Host"

    def test_vulnerability_label(self) -> None:
        assert _label_for(NodeKind.VULNERABILITY) == "Vulnerability"

    def test_all_node_labels_covers_all_kinds(self) -> None:
        assert set(_ALL_NODE_LABELS) == {k.value for k in NodeKind}
        assert "Host" in _ALL_NODE_LABELS


class TestNeo4jConfig:
    def test_from_env_happy_path_defaults_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DECEPTICON_NEO4J_DATABASE", raising=False)
        monkeypatch.setenv("DECEPTICON_NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("DECEPTICON_NEO4J_USER", "neo4j")
        monkeypatch.setenv("DECEPTICON_NEO4J_PASSWORD", "secret")
        cfg = Neo4jConfig.from_env()
        assert cfg.uri == "bolt://localhost:7687"
        assert cfg.user == "neo4j"
        assert cfg.password == "secret"
        assert cfg.database == "neo4j"

    def test_from_env_custom_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_NEO4J_URI", "bolt://x:7687")
        monkeypatch.setenv("DECEPTICON_NEO4J_USER", "u")
        monkeypatch.setenv("DECEPTICON_NEO4J_PASSWORD", "p")
        monkeypatch.setenv("DECEPTICON_NEO4J_DATABASE", "kg")
        cfg = Neo4jConfig.from_env()
        assert cfg.database == "kg"

    def test_from_env_whitespace_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_NEO4J_URI", " bolt://x:7687 ")
        monkeypatch.setenv("DECEPTICON_NEO4J_USER", " u ")
        monkeypatch.setenv("DECEPTICON_NEO4J_PASSWORD", " p ")
        cfg = Neo4jConfig.from_env()
        assert cfg.uri == "bolt://x:7687"
        assert cfg.user == "u"
        assert cfg.password == "p"

    def test_from_env_empty_database_falls_back_to_neo4j(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DECEPTICON_NEO4J_URI", "bolt://x")
        monkeypatch.setenv("DECEPTICON_NEO4J_USER", "u")
        monkeypatch.setenv("DECEPTICON_NEO4J_PASSWORD", "p")
        monkeypatch.setenv("DECEPTICON_NEO4J_DATABASE", "")
        cfg = Neo4jConfig.from_env()
        assert cfg.database == "neo4j"

    def test_from_env_all_missing_raises_with_all_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DECEPTICON_NEO4J_URI", raising=False)
        monkeypatch.delenv("DECEPTICON_NEO4J_USER", raising=False)
        monkeypatch.delenv("DECEPTICON_NEO4J_PASSWORD", raising=False)
        with pytest.raises(Neo4jUnavailableError) as exc_info:
            Neo4jConfig.from_env()
        msg = str(exc_info.value)
        assert "DECEPTICON_NEO4J_URI" in msg
        assert "DECEPTICON_NEO4J_USER" in msg
        assert "DECEPTICON_NEO4J_PASSWORD" in msg

    def test_from_env_partial_missing_raises_listing_missing_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DECEPTICON_NEO4J_URI", "bolt://x")
        monkeypatch.delenv("DECEPTICON_NEO4J_USER", raising=False)
        monkeypatch.delenv("DECEPTICON_NEO4J_PASSWORD", raising=False)
        with pytest.raises(Neo4jUnavailableError) as exc_info:
            Neo4jConfig.from_env()
        msg = str(exc_info.value)
        assert "DECEPTICON_NEO4J_URI" not in msg
        assert "DECEPTICON_NEO4J_USER" in msg
        assert "DECEPTICON_NEO4J_PASSWORD" in msg


class TestNeo4jStoreInit:
    def test_init_import_failure_raises_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(__import__("sys").modules, "neo4j", None)
        cfg = Neo4jConfig(uri="bolt://x", user="u", password="p")
        with pytest.raises(Neo4jUnavailableError) as exc_info:
            Neo4jStore(cfg)
        assert "neo4j" in str(exc_info.value).lower()

    def test_init_happy_path_calls_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_driver = MagicMock()
        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = MagicMock()  # type: ignore[attr-defined]
        fake_neo4j.GraphDatabase.driver = MagicMock(return_value=fake_driver)  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "neo4j", fake_neo4j)
        cfg = Neo4jConfig(uri="bolt://host:7687", user="neo4j", password="s3cr3t", database="mydb")
        store = Neo4jStore(cfg)
        fake_neo4j.GraphDatabase.driver.assert_called_once_with(
            "bolt://host:7687", auth=("neo4j", "s3cr3t")
        )
        assert store._database == "mydb"

    def test_from_env_composes_config_and_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_driver = MagicMock()
        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = MagicMock()  # type: ignore[attr-defined]
        fake_neo4j.GraphDatabase.driver = MagicMock(return_value=fake_driver)  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "neo4j", fake_neo4j)
        monkeypatch.setenv("DECEPTICON_NEO4J_URI", "bolt://env:7687")
        monkeypatch.setenv("DECEPTICON_NEO4J_USER", "envuser")
        monkeypatch.setenv("DECEPTICON_NEO4J_PASSWORD", "envpass")
        monkeypatch.delenv("DECEPTICON_NEO4J_DATABASE", raising=False)
        store = Neo4jStore.from_env()
        assert store._database == "neo4j"
        fake_neo4j.GraphDatabase.driver.assert_called_once()


class TestNeo4jStoreClose:
    def test_close_calls_driver_close(self) -> None:
        driver = _FakeDriver()
        store = _make_store(driver)
        store.close()
        assert driver.close_called


class TestEnsureSchema:
    def test_ensure_schema_runs_expected_statement_count(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.ensure_schema()
        assert len(session.runs) == 26

    def test_ensure_schema_includes_known_constraint(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.ensure_schema()
        all_stmts = [r[0] for r in session.runs]
        assert any("host_ip" in s for s in all_stmts)

    def test_ensure_schema_includes_known_index(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.ensure_schema()
        all_stmts = [r[0] for r in session.runs]
        assert any("host_explored" in s for s in all_stmts)


class TestRevision:
    def test_revision_returns_float_from_record(self) -> None:
        session = _FakeSession(results=[_FakeResult([], single_row={"rev": 42.0})])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.revision()
        assert result == 42.0

    def test_revision_record_is_none_returns_zero(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.revision()
        assert result == 0.0

    def test_revision_get_returns_none_falls_back_to_zero(self) -> None:
        session = _FakeSession(results=[_FakeResult([], single_row={"rev": None})])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.revision()
        assert result == 0.0

    def test_revision_non_floatable_returns_zero(self) -> None:
        session = _FakeSession(results=[_FakeResult([], single_row={"rev": "not-a-float"})])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.revision()
        assert result == 0.0

    def test_revision_passes_all_node_labels(self) -> None:
        session = _FakeSession(results=[_FakeResult([], single_row={"rev": 1.0})])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.revision()
        assert len(session.runs) == 1
        _query, params = session.runs[0]
        assert params.get("labels") == _ALL_NODE_LABELS


class TestUpsertNode:
    def test_upsert_node_runs_merge_query_with_correct_params(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession()
            driver = _FakeDriver(sessions=[session])
            store = _make_store(driver)
            node = Node.make(NodeKind.HOST, "10.0.0.1", key="host::10.0.0.1")
            store.upsert_node(node)
            assert len(session.runs) == 1
            query, params = session.runs[0]
            assert "MERGE (n:Host" in query
            assert "n.engagement = $engagement" in query
            assert params["id"] == node.id
            assert params["kind"] == "Host"
            assert params["engagement"] == "acme"
            assert params["key"] == "host::10.0.0.1"
            props_dict = json.loads(params["props"])
            assert props_dict["engagement"] == "acme"
        finally:
            reset_active_engagement(token)

    def test_upsert_node_key_falls_back_to_id_when_not_in_props(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        node = Node.make(NodeKind.HOST, "10.0.0.2")
        store.upsert_node(node)
        _query, params = session.runs[0]
        assert params["key"] == node.id

    def test_upsert_node_promotes_indexed_scalar_props(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        node = Node.make(NodeKind.VULNERABILITY, "v1", severity="high", validated=True)
        store.upsert_node(node)
        query, params = session.runs[0]
        assert "n += $promoted" in query
        assert params["promoted"] == {"severity": "high", "validated": True}

    def test_upsert_node_promoted_excludes_non_whitelisted(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        node = Node.make(NodeKind.VULNERABILITY, "v2", severity="medium", notes="ignore me")
        store.upsert_node(node)
        _query, params = session.runs[0]
        assert params["promoted"] == {"severity": "medium"}


class TestUpsertEdge:
    def test_upsert_edge_runs_merge_query_with_correct_params(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession()
            driver = _FakeDriver(sessions=[session])
            store = _make_store(driver)
            src = Node.make(NodeKind.HOST, "h1")
            dst = Node.make(NodeKind.VULNERABILITY, "v1")
            edge = Edge.make(src.id, dst.id, EdgeKind.HAS_VULN)
            store.upsert_edge(edge)
            assert len(session.runs) == 1
            query, params = session.runs[0]
            assert "MERGE (src)-[r:HAS_VULN" in query
            assert "r.engagement = $engagement" in query
            assert params["src_id"] == src.id
            assert params["dst_id"] == dst.id
            assert params["edge_id"] == edge.id
            assert params["kind"] == "HAS_VULN"
            assert params["engagement"] == "acme"
        finally:
            reset_active_engagement(token)


class TestBatchUpsertNodes:
    def test_empty_list_returns_zero_and_no_run(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.batch_upsert_nodes([])
        assert result == 0
        assert len(session.runs) == 0

    def test_mixed_kinds_groups_by_label_and_returns_total(self) -> None:
        token = set_active_engagement("eng1")
        try:
            session = _FakeSession()
            driver = _FakeDriver(sessions=[session])
            store = _make_store(driver)
            h1 = Node.make(NodeKind.HOST, "h1")
            h2 = Node.make(NodeKind.HOST, "h2")
            v1 = Node.make(NodeKind.VULNERABILITY, "v1")
            result = store.batch_upsert_nodes([h1, h2, v1])
            assert result == 3
            assert len(session.runs) == 2
            all_queries = [r[0] for r in session.runs]
            assert any("UNWIND $batch AS row" in q for q in all_queries)
            assert any("MERGE (n:Host" in q for q in all_queries)
            assert any("MERGE (n:Vulnerability" in q for q in all_queries)
        finally:
            reset_active_engagement(token)

    def test_batch_rows_include_engagement(self) -> None:
        token = set_active_engagement("test-eng")
        try:
            session = _FakeSession()
            driver = _FakeDriver(sessions=[session])
            store = _make_store(driver)
            node = Node.make(NodeKind.HOST, "h1")
            store.batch_upsert_nodes([node])
            _query, params = session.runs[0]
            batch = params.get("batch", [])
            assert len(batch) == 1
            assert batch[0]["engagement"] == "test-eng"
        finally:
            reset_active_engagement(token)

    def test_batch_rows_include_promoted_map_and_query(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        node = Node.make(NodeKind.VULNERABILITY, "v1", severity="high", validated=True)
        store.batch_upsert_nodes([node])
        query, params = session.runs[0]
        assert "n += row.promoted" in query
        batch = params.get("batch", [])
        assert len(batch) == 1
        assert batch[0]["promoted"] == {"severity": "high", "validated": True}


class TestBatchUpsertEdges:
    def test_empty_list_returns_zero_and_no_run(self) -> None:
        session = _FakeSession()
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.batch_upsert_edges([])
        assert result == 0
        assert len(session.runs) == 0

    def test_two_edges_different_kinds_grouped_and_counted(self) -> None:
        token = set_active_engagement("eng2")
        try:
            session = _FakeSession()
            driver = _FakeDriver(sessions=[session])
            store = _make_store(driver)
            src = Node.make(NodeKind.HOST, "h1")
            dst1 = Node.make(NodeKind.VULNERABILITY, "v1")
            dst2 = Node.make(NodeKind.SERVICE, "s1")
            e1 = Edge.make(src.id, dst1.id, EdgeKind.HAS_VULN)
            e2 = Edge.make(src.id, dst2.id, EdgeKind.HOSTS)
            result = store.batch_upsert_edges([e1, e2])
            assert result == 2
            assert len(session.runs) == 2
            all_queries = [r[0] for r in session.runs]
            assert any("MATCH (src {id: row.src_id})" in q for q in all_queries)
            assert any("MERGE (src)-[r:HAS_VULN" in q for q in all_queries)
            assert any("MERGE (src)-[r:HOSTS" in q for q in all_queries)
        finally:
            reset_active_engagement(token)


class TestQueryNeighbors:
    def test_invalid_direction_raises_value_error(self) -> None:
        driver = _FakeDriver()
        store = _make_store(driver)
        with pytest.raises(ValueError):
            store.query_neighbors("n1", direction="sideways")

    def test_direction_out_generates_outgoing_pattern(self) -> None:
        row_data = {
            "id": "nbr1",
            "kind": "Service",
            "label": "svc",
            "props": '{"port": 80}',
            "created_at": 1.0,
            "updated_at": 2.0,
            "edge_id": "e1",
            "edge_type": "HOSTS",
            "edge_kind": "HOSTS",
            "edge_weight": 1.0,
            "edge_props": "{}",
        }
        session = _FakeSession(results=[_FakeResult([row_data])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        results = store.query_neighbors("n1", direction="out")
        assert len(results) == 1
        query, _params = session.runs[0]
        assert "(src {id: $node_id})-[r]->(nbr)" in query

    def test_direction_in_generates_incoming_pattern(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.query_neighbors("n1", direction="in")
        query, _params = session.runs[0]
        assert "(nbr)-[r]->(src {id: $node_id})" in query

    def test_direction_both_generates_undirected_pattern(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.query_neighbors("n1", direction="both")
        query, _params = session.runs[0]
        assert "(src {id: $node_id})-[r]-(nbr)" in query

    def test_edge_kind_filter_adds_where_clause_and_uppercases(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.query_neighbors("n1", edge_kind="has_vuln")
        query, params = session.runs[0]
        assert "WHERE type(r) = $edge_kind" in query
        assert params["edge_kind"] == "HAS_VULN"

    def test_no_edge_kind_omits_where_clause(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.query_neighbors("n1")
        query, params = session.runs[0]
        assert "WHERE type(r)" not in query
        assert "edge_kind" not in params

    def test_row_props_decoded_and_floats_coerced(self) -> None:
        row_data = {
            "id": "nbr1",
            "kind": "Service",
            "label": "svc",
            "props": '{"port": 80}',
            "created_at": None,
            "updated_at": None,
            "edge_id": "e1",
            "edge_type": "HOSTS",
            "edge_kind": "HOSTS",
            "edge_weight": None,
            "edge_props": "{}",
        }
        session = _FakeSession(results=[_FakeResult([row_data])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        results = store.query_neighbors("n1")
        assert results[0]["node"]["props"] == {"port": 80}
        assert results[0]["node"]["created_at"] == 0.0
        assert results[0]["edge"]["weight"] == 1.0


class TestQueryByKind:
    def test_valid_kind_value_generates_correct_label_query(self) -> None:
        row_data = {
            "id": "h1",
            "kind": "Host",
            "label": "10.0.0.1",
            "props": "{}",
            "created_at": 0.0,
            "updated_at": 0.0,
        }
        session = _FakeSession(results=[_FakeResult([row_data])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        results = store.query_by_kind("Host")
        assert len(results) == 1
        assert results[0]["id"] == "h1"
        query, _params = session.runs[0]
        assert "MATCH (n:Host)" in query

    def test_vulnerability_kind_accepted(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        results = store.query_by_kind("Vulnerability")
        assert results == []

    def test_invalid_kind_raises_value_error_with_message(self) -> None:
        driver = _FakeDriver()
        store = _make_store(driver)
        with pytest.raises(ValueError, match="unknown node kind/label"):
            store.query_by_kind("Bogus")

    def test_returned_rows_have_decoded_props_and_float_timestamps(self) -> None:
        row_data = {
            "id": "h2",
            "kind": "Host",
            "label": "myhost",
            "props": '{"ip": "1.2.3.4"}',
            "created_at": None,
            "updated_at": None,
        }
        session = _FakeSession(results=[_FakeResult([row_data])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        results = store.query_by_kind("Host")
        assert results[0]["props"] == {"ip": "1.2.3.4"}
        assert results[0]["created_at"] == 0.0


class TestQueryCustom:
    def test_runs_cypher_with_params_and_returns_dicts(self) -> None:
        row_data = {"n": "val1", "x": 2}
        session = _FakeSession(results=[_FakeResult([row_data])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        results = store.query_custom("MATCH (n) RETURN n", {"p": 1})
        assert len(results) == 1
        assert results[0]["n"] == "val1"
        _query, params = session.runs[0]
        assert params.get("parameters") == {"p": 1}

    def test_params_none_passes_empty_dict(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        store.query_custom("MATCH (n) RETURN n")
        _query, params = session.runs[0]
        assert params.get("parameters") == {}


class TestStats:
    def test_node_and_edge_counts_aggregated(self) -> None:
        node_rows = [{"label": "Host", "cnt": 3}, {"label": "Service", "cnt": 0}]
        edge_rows = [{"rel_type": "HAS_VULN", "cnt": 2}]
        node_session = _FakeSession(results=[_FakeResult(node_rows)])
        edge_session = _FakeSession(results=[_FakeResult(edge_rows)])
        driver = _FakeDriver(sessions=[node_session, edge_session])
        store = _make_store(driver)
        result = store.stats()
        assert result["nodes"] == 3
        assert result["edges"] == 2
        assert result["node.Host"] == 3
        assert result["edge.HAS_VULN"] == 2

    def test_zero_count_rows_not_included_in_result(self) -> None:
        node_rows = [{"label": "Host", "cnt": 3}, {"label": "Service", "cnt": 0}]
        edge_rows: list[dict[str, Any]] = []
        node_session = _FakeSession(results=[_FakeResult(node_rows)])
        edge_session = _FakeSession(results=[_FakeResult(edge_rows)])
        driver = _FakeDriver(sessions=[node_session, edge_session])
        store = _make_store(driver)
        result = store.stats()
        assert "node.Service" not in result


class TestRemoveNode:
    def test_record_present_returns_removed_count(self) -> None:
        session = _FakeSession(results=[_FakeResult([], single_row={"removed": 4})])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.remove_node("n1")
        assert result == 4
        query, params = session.runs[0]
        assert "DETACH DELETE n" in query
        assert params.get("node_id") == "n1"

    def test_record_none_returns_zero(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        result = store.remove_node("missing")
        assert result == 0


class TestLoadGraph:
    def _make_load_session(
        self,
        node_rows: list[dict[str, Any]],
        edge_rows: list[dict[str, Any]],
    ) -> _FakeSession:
        node_result = _FakeResult(node_rows)
        edge_result = _FakeResult(edge_rows)
        return _FakeSession(results=[node_result, edge_result])

    def test_valid_node_and_edge_loaded(self) -> None:
        h1 = Node.make(NodeKind.HOST, "h1")
        h2 = Node.make(NodeKind.HOST, "h2")
        node_rows = [
            {
                "id": h1.id,
                "kind": "Host",
                "label": "h1",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
            {
                "id": h2.id,
                "kind": "Host",
                "label": "h2",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        ]
        e1 = Edge.make(h1.id, h2.id, EdgeKind.HOSTS)
        edge_rows = [
            {
                "id": e1.id,
                "src": h1.id,
                "dst": h2.id,
                "kind": "HOSTS",
                "weight": 1.0,
                "props": "{}",
                "created_at": 0.0,
            },
        ]
        session = self._make_load_session(node_rows, edge_rows)
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert isinstance(graph, KnowledgeGraph)
        assert h1.id in graph.nodes
        assert h2.id in graph.nodes
        assert e1.id in graph.edges

    def test_node_with_unknown_kind_skipped(self) -> None:
        node_rows = [
            {
                "id": "n1",
                "kind": "Bogus",
                "label": "n1",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        ]
        session = self._make_load_session(node_rows, [])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert "n1" not in graph.nodes

    def test_node_with_non_str_id_or_kind_skipped(self) -> None:
        node_rows = [
            {
                "id": None,
                "kind": "Host",
                "label": "n1",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        ]
        session = self._make_load_session(node_rows, [])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert len(graph.nodes) == 0

    def test_edge_with_unknown_kind_skipped(self) -> None:
        h1 = Node.make(NodeKind.HOST, "h1")
        h2 = Node.make(NodeKind.HOST, "h2")
        node_rows = [
            {
                "id": h1.id,
                "kind": "Host",
                "label": "h1",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
            {
                "id": h2.id,
                "kind": "Host",
                "label": "h2",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        ]
        edge_rows = [
            {
                "id": "e1",
                "src": h1.id,
                "dst": h2.id,
                "kind": "BOGUS_EDGE",
                "weight": 1.0,
                "props": "{}",
                "created_at": 0.0,
            },
        ]
        session = self._make_load_session(node_rows, edge_rows)
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert "e1" not in graph.edges

    def test_edge_with_dangling_src_skipped(self) -> None:
        h1 = Node.make(NodeKind.HOST, "h1")
        node_rows = [
            {
                "id": h1.id,
                "kind": "Host",
                "label": "h1",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        ]
        edge_rows = [
            {
                "id": "e1",
                "src": "missing-id",
                "dst": h1.id,
                "kind": "HOSTS",
                "weight": 1.0,
                "props": "{}",
                "created_at": 0.0,
            },
        ]
        session = self._make_load_session(node_rows, edge_rows)
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert "e1" not in graph.edges

    def test_edge_with_non_str_fields_skipped(self) -> None:
        h1 = Node.make(NodeKind.HOST, "h1")
        h2 = Node.make(NodeKind.HOST, "h2")
        node_rows = [
            {
                "id": h1.id,
                "kind": "Host",
                "label": "h1",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
            {
                "id": h2.id,
                "kind": "Host",
                "label": "h2",
                "props": "{}",
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        ]
        edge_rows = [
            {
                "id": None,
                "src": h1.id,
                "dst": h2.id,
                "kind": "HOSTS",
                "weight": 1.0,
                "props": "{}",
                "created_at": 0.0,
            },
        ]
        session = self._make_load_session(node_rows, edge_rows)
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert len(graph.edges) == 0

    def test_load_graph_returns_knowledge_graph_instance(self) -> None:
        session = self._make_load_session([], [])
        driver = _FakeDriver(sessions=[session])
        store = _make_store(driver)
        graph = store.load_graph()
        assert isinstance(graph, KnowledgeGraph)


class TestEdgeCost:
    def test_upsert_edge_writes_computed_cost(self) -> None:
        session = _FakeSession()
        store = _make_store(_FakeDriver(sessions=[session]))
        edge = Edge.make("h1", "v1", EdgeKind.HAS_VULN)
        store.upsert_edge(edge)
        query, _params = session.runs[0]
        assert "r.cost =" in query
        assert "coalesce(dst.severity, '')" in query
        assert "coalesce(dst.validated, false)" in query
        assert "WHEN 'critical' THEN 0.4" in query
        assert "$weight > 0.05" in query

    def test_batch_upsert_edges_writes_computed_cost(self) -> None:
        session = _FakeSession()
        store = _make_store(_FakeDriver(sessions=[session]))
        e1 = Edge.make("h1", "v1", EdgeKind.HAS_VULN)
        store.batch_upsert_edges([e1])
        query, _params = session.runs[0]
        assert "r.cost =" in query
        assert "row.weight > 0.05" in query
        assert "coalesce(dst.severity, '')" in query

    def test_edge_cost_expr_covers_every_multiplier(self) -> None:
        expr = _edge_cost_expr("$weight")
        for sev, mult in SEVERITY_COST_MULTIPLIER.items():
            assert f"WHEN '{sev.value}' THEN {mult}" in expr
        assert "ELSE 1.0 END" in expr
        assert "$weight" in expr


class TestEngagementScopedReads:
    def _load_session(self) -> _FakeSession:
        return _FakeSession(results=[_FakeResult([]), _FakeResult([])])

    def test_query_by_kind_unscoped_when_no_active_engagement(self) -> None:
        session = _FakeSession(results=[_FakeResult([])])
        store = _make_store(_FakeDriver(sessions=[session]))
        store.query_by_kind("Host")
        query, params = session.runs[0]
        assert "engagement" not in query
        assert "engagement" not in params

    def test_query_by_kind_scoped_to_active_engagement(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession(results=[_FakeResult([])])
            store = _make_store(_FakeDriver(sessions=[session]))
            store.query_by_kind("Host")
            query, params = session.runs[0]
            assert "WHERE n.engagement = $engagement" in query
            assert params["engagement"] == "acme"
        finally:
            reset_active_engagement(token)

    def test_query_by_kind_all_engagements_opts_out(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession(results=[_FakeResult([])])
            store = _make_store(_FakeDriver(sessions=[session]))
            store.query_by_kind("Host", all_engagements=True)
            query, params = session.runs[0]
            assert "engagement" not in query
            assert "engagement" not in params
        finally:
            reset_active_engagement(token)

    # ── query_neighbors ──────────────────────────────────────────────────
    def test_query_neighbors_scoped_filters_edge_and_neighbor(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession(results=[_FakeResult([])])
            store = _make_store(_FakeDriver(sessions=[session]))
            store.query_neighbors("n1")
            query, params = session.runs[0]
            assert "r.engagement = $engagement" in query
            assert "nbr.engagement = $engagement" in query
            assert params["engagement"] == "acme"
        finally:
            reset_active_engagement(token)

    def test_query_neighbors_combines_engagement_with_edge_kind(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession(results=[_FakeResult([])])
            store = _make_store(_FakeDriver(sessions=[session]))
            store.query_neighbors("n1", edge_kind="has_vuln")
            query, params = session.runs[0]
            assert "type(r) = $edge_kind" in query
            assert "r.engagement = $engagement" in query
            assert " AND " in query
            assert params["edge_kind"] == "HAS_VULN"
            assert params["engagement"] == "acme"
        finally:
            reset_active_engagement(token)

    def test_query_neighbors_all_engagements_opts_out(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = _FakeSession(results=[_FakeResult([])])
            store = _make_store(_FakeDriver(sessions=[session]))
            store.query_neighbors("n1", all_engagements=True)
            query, params = session.runs[0]
            assert "engagement" not in query
            assert "engagement" not in params
        finally:
            reset_active_engagement(token)

    # ── load_graph (the graph_transaction load path) ─────────────────────
    def test_load_graph_unscoped_when_no_active_engagement(self) -> None:
        session = self._load_session()
        store = _make_store(_FakeDriver(sessions=[session]))
        store.load_graph()
        node_query, node_params = session.runs[0]
        edge_query, edge_params = session.runs[1]
        assert "n.engagement" not in node_query
        assert "r.engagement" not in edge_query
        assert "engagement" not in node_params
        assert "engagement" not in edge_params

    def test_load_graph_scoped_filters_nodes_and_edges(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = self._load_session()
            store = _make_store(_FakeDriver(sessions=[session]))
            store.load_graph()
            node_query, node_params = session.runs[0]
            edge_query, edge_params = session.runs[1]
            assert "n.engagement = $engagement" in node_query
            assert "r.engagement = $engagement" in edge_query
            assert node_params["engagement"] == "acme"
            assert edge_params["engagement"] == "acme"
        finally:
            reset_active_engagement(token)

    def test_load_graph_all_engagements_opts_out(self) -> None:
        token = set_active_engagement("acme")
        try:
            session = self._load_session()
            store = _make_store(_FakeDriver(sessions=[session]))
            store.load_graph(all_engagements=True)
            node_query, node_params = session.runs[0]
            assert "n.engagement" not in node_query
            assert "engagement" not in node_params
        finally:
            reset_active_engagement(token)
