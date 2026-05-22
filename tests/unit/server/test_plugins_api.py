"""Tests for the runtime plugin-bundle activation API.

``decepticon/server/plugins_api.py`` is mounted into the LangGraph
platform and toggles agent bundles on/off at runtime. The route handlers
import ``langgraph_api.*`` / ``langgraph_runtime.*`` *lazily inside the
function bodies* precisely so the module stays unit-testable; these tests
exploit that by installing minimal fake modules into ``sys.modules``
before issuing each request. No real LangGraph platform, database, or
agent-graph import happens.

The pure helpers (``_path_to_module``, ``_resolve_bundle``) need no
stubbing at all.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from decepticon.graph_registry import _BUNDLE_TO_GRAPHS
from decepticon.server import plugins_api
from decepticon.server.plugins_api import (
    _path_to_module,
    _resolve_bundle,
    app,
)

client = TestClient(app)

# Names the route handlers import lazily. The fixture below removes any
# real instances around each test so a partially-importable real package
# can't shadow our fakes (and our fakes can't leak out).
_STUBBED_MODULES = (
    "langgraph_api",
    "langgraph_api.graph",
    "langgraph_api.feature_flags",
    "langgraph_api.grpc",
    "langgraph_api.grpc.ops",
    "langgraph_runtime",
    "langgraph_runtime.database",
    "langgraph_runtime.ops",
)


@pytest.fixture
def _clean_lg_modules() -> Iterator[None]:
    """Snapshot and clear the LangGraph modules the routes import lazily.

    Each test that exercises a route installs its own fakes; this fixture
    just guarantees a clean slate before and faithful restore after.
    """
    saved = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
    for name in _STUBBED_MODULES:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


def _install_graph_module(graphs: dict[str, Any], register_calls: list[Any]) -> None:
    """Install a fake ``langgraph_api.graph`` exposing the names the
    enable/list routes read: ``GRAPHS`` and an async ``register_graph``."""

    async def register_graph(graph_id: str, graph_obj: Any, config: Any = None) -> None:
        register_calls.append((graph_id, graph_obj, config))

    mod = types.ModuleType("langgraph_api.graph")
    mod.GRAPHS = graphs  # pyright: ignore[reportAttributeAccessIssue]
    mod.register_graph = register_graph  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["langgraph_api.graph"] = mod


# ── _path_to_module ──────────────────────────────────────────────────────


def test_path_to_module_happy_path() -> None:
    module, variable = _path_to_module("./decepticon/agents/plugins/vulnresearch.py:graph")
    assert module == "decepticon.agents.plugins.vulnresearch"
    assert variable == "graph"


def test_path_to_module_strips_leading_dot_slash_and_py_suffix() -> None:
    module, variable = _path_to_module("decepticon/agents/standard/recon.py:graph")
    assert module == "decepticon.agents.standard.recon"
    assert variable == "graph"


def test_path_to_module_missing_variable_suffix_raises_value_error() -> None:
    with pytest.raises(ValueError, match="missing ':variable' suffix"):
        _path_to_module("./decepticon/agents/plugins/vulnresearch.py")


# ── _resolve_bundle ──────────────────────────────────────────────────────


def test_resolve_bundle_known_returns_graph_map() -> None:
    resolved = _resolve_bundle("plugins")
    assert resolved is _BUNDLE_TO_GRAPHS["plugins"]


def test_resolve_bundle_unknown_raises_404() -> None:
    with pytest.raises(HTTPException) as exc:
        _resolve_bundle("nonexistent-bundle")
    assert exc.value.status_code == 404
    assert "unknown bundle" in str(exc.value.detail)


# ── GET /_decepticon/bundles ─────────────────────────────────────────────


def test_list_bundles_all_registered_reports_enabled_true() -> None:
    all_graph_ids = {gid for graphs in _BUNDLE_TO_GRAPHS.values() for gid in graphs}
    with patch.object(plugins_api, "_registered_graph_ids", return_value=all_graph_ids):
        resp = client.get("/_decepticon/bundles")
    assert resp.status_code == 200
    bundles = {b["name"]: b for b in resp.json()["bundles"]}
    assert set(bundles) == set(_BUNDLE_TO_GRAPHS)
    for name, bundle in bundles.items():
        assert bundle["enabled"] is True
        assert bundle["graphs"] == list(_BUNDLE_TO_GRAPHS[name])


def test_list_bundles_partial_registration_reports_enabled_false() -> None:
    # Register only the first graph of the 'plugins' bundle — partial state
    # must report enabled=False.
    plugin_graphs = list(_BUNDLE_TO_GRAPHS["plugins"])
    with patch.object(plugins_api, "_registered_graph_ids", return_value={plugin_graphs[0]}):
        resp = client.get("/_decepticon/bundles")
    assert resp.status_code == 200
    bundles = {b["name"]: b for b in resp.json()["bundles"]}
    assert bundles["plugins"]["enabled"] is False


def test_list_bundles_nothing_registered_reports_enabled_false() -> None:
    with patch.object(plugins_api, "_registered_graph_ids", return_value=set()):
        resp = client.get("/_decepticon/bundles")
    assert resp.status_code == 200
    for bundle in resp.json()["bundles"]:
        assert bundle["enabled"] is False


# ── POST /_decepticon/bundles/{name}/enable ──────────────────────────────


def test_enable_bundle_registers_every_graph(_clean_lg_modules: None) -> None:
    register_calls: list[Any] = []
    _install_graph_module({}, register_calls)
    sentinel = object()
    with patch.object(plugins_api, "_load_graph", return_value=sentinel):
        resp = client.post("/_decepticon/bundles/plugins/enable")
    assert resp.status_code == 200
    body = resp.json()
    expected = list(_BUNDLE_TO_GRAPHS["plugins"])
    assert body["bundle"] == "plugins"
    assert body["enabled"] is True
    assert body["graphs"] == expected
    assert body["skipped"] == []
    assert [gid for gid, _, _ in register_calls] == expected
    assert all(obj is sentinel for _, obj, _ in register_calls)


def test_enable_bundle_skips_already_registered_graphs(
    _clean_lg_modules: None,
) -> None:
    plugin_graphs = list(_BUNDLE_TO_GRAPHS["plugins"])
    already = plugin_graphs[0]
    register_calls: list[Any] = []
    # The first graph is already present in GRAPHS -> it must be skipped,
    # not re-registered.
    _install_graph_module({already: object()}, register_calls)
    with patch.object(plugins_api, "_load_graph", return_value=object()):
        resp = client.post("/_decepticon/bundles/plugins/enable")
    assert resp.status_code == 200
    body = resp.json()
    assert body["skipped"] == [already]
    assert body["graphs"] == plugin_graphs[1:]
    assert already not in [gid for gid, _, _ in register_calls]


def test_enable_bundle_unknown_name_is_404(_clean_lg_modules: None) -> None:
    _install_graph_module({}, [])
    resp = client.post("/_decepticon/bundles/does-not-exist/enable")
    assert resp.status_code == 404
    assert "unknown bundle" in resp.json()["detail"]


def test_enable_bundle_register_graph_failure_is_500(
    _clean_lg_modules: None,
) -> None:
    async def failing_register(graph_id: str, graph_obj: Any, config: Any = None) -> None:
        raise RuntimeError("registry exploded")

    mod = types.ModuleType("langgraph_api.graph")
    mod.GRAPHS = {}  # pyright: ignore[reportAttributeAccessIssue]
    mod.register_graph = failing_register  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["langgraph_api.graph"] = mod

    with patch.object(plugins_api, "_load_graph", return_value=object()):
        resp = client.post("/_decepticon/bundles/plugins/enable")
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "register_graph" in detail
    assert "registry exploded" in detail


# ── POST /_decepticon/bundles/{name}/disable ─────────────────────────────


def test_disable_bundle_standard_is_400_before_any_import() -> None:
    # The 'standard' guard runs before the lazy langgraph imports, so this
    # needs no stubbing at all.
    resp = client.post("/_decepticon/bundles/standard/disable")
    assert resp.status_code == 400
    assert "cannot be disabled" in resp.json()["detail"]


def test_disable_bundle_unknown_name_is_404(_clean_lg_modules: None) -> None:
    _install_disable_stubs(graphs={}, deleted=[])
    resp = client.post("/_decepticon/bundles/does-not-exist/disable")
    assert resp.status_code == 404
    assert "unknown bundle" in resp.json()["detail"]


def _install_disable_stubs(
    *,
    graphs: dict[str, Any],
    deleted: list[Any],
    postgres: bool = False,
    delete_raises: bool = False,
) -> None:
    """Install the full set of fake modules ``disable_bundle`` imports.

    ``disable_bundle`` reaches for ``langgraph_api.graph`` (GRAPHS,
    NAMESPACE_GRAPH, SYSTEM_ASSISTANT_IDS), ``langgraph_runtime.database``
    (connect), ``langgraph_api.feature_flags`` (IS_POSTGRES_OR_GRPC_BACKEND)
    and one of the two ``Assistants`` providers.

    ``postgres`` picks which provider module the route imports
    (``langgraph_api.grpc.ops`` vs ``langgraph_runtime.ops``).
    ``delete_raises`` makes ``Assistants.delete`` blow up so the
    best-effort cleanup ``except`` branch is exercised.
    """
    import uuid

    graph_mod = types.ModuleType("langgraph_api.graph")
    graph_mod.GRAPHS = graphs  # pyright: ignore[reportAttributeAccessIssue]
    graph_mod.NAMESPACE_GRAPH = uuid.NAMESPACE_DNS  # pyright: ignore[reportAttributeAccessIssue]
    graph_mod.SYSTEM_ASSISTANT_IDS = set()  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["langgraph_api.graph"] = graph_mod

    flags_mod = types.ModuleType("langgraph_api.feature_flags")
    flags_mod.IS_POSTGRES_OR_GRPC_BACKEND = postgres  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["langgraph_api.feature_flags"] = flags_mod

    class _Conn:
        async def __aenter__(self) -> _Conn:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    def connect() -> _Conn:
        return _Conn()

    db_mod = types.ModuleType("langgraph_runtime.database")
    db_mod.connect = connect  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["langgraph_runtime.database"] = db_mod

    class _Assistants:
        @staticmethod
        async def delete(conn: Any, assistant_id: Any) -> Any:
            deleted.append(assistant_id)
            if delete_raises:
                raise RuntimeError("assistants row delete failed")

            async def _empty() -> Any:
                return
                yield  # pragma: no cover  — makes this an async generator

            return _empty()

    # Route imports from langgraph_api.grpc.ops when postgres, else
    # langgraph_runtime.ops. Install the matching one (and a parent
    # package for the grpc namespace so the import machinery is happy).
    if postgres:
        grpc_pkg = types.ModuleType("langgraph_api.grpc")
        sys.modules["langgraph_api.grpc"] = grpc_pkg
        grpc_ops = types.ModuleType("langgraph_api.grpc.ops")
        grpc_ops.Assistants = _Assistants  # pyright: ignore[reportAttributeAccessIssue]
        sys.modules["langgraph_api.grpc.ops"] = grpc_ops
    else:
        ops_mod = types.ModuleType("langgraph_runtime.ops")
        ops_mod.Assistants = _Assistants  # pyright: ignore[reportAttributeAccessIssue]
        sys.modules["langgraph_runtime.ops"] = ops_mod


def test_disable_bundle_happy_path_removes_graphs(
    _clean_lg_modules: None,
) -> None:
    plugin_graphs = list(_BUNDLE_TO_GRAPHS["plugins"])
    live_graphs = {gid: object() for gid in plugin_graphs}
    deleted: list[Any] = []
    _install_disable_stubs(graphs=live_graphs, deleted=deleted)

    resp = client.post("/_decepticon/bundles/plugins/disable")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bundle"] == "plugins"
    assert body["enabled"] is False
    assert body["graphs"] == plugin_graphs
    assert body["skipped"] == []
    # GRAPHS entries were removed and one Assistants.delete per graph fired.
    assert live_graphs == {}
    assert len(deleted) == len(plugin_graphs)


def test_disable_bundle_skips_graphs_not_registered(
    _clean_lg_modules: None,
) -> None:
    plugin_graphs = list(_BUNDLE_TO_GRAPHS["plugins"])
    # Only the first graph is live; the rest must be reported as skipped.
    live_graphs = {plugin_graphs[0]: object()}
    deleted: list[Any] = []
    _install_disable_stubs(graphs=live_graphs, deleted=deleted)

    resp = client.post("/_decepticon/bundles/plugins/disable")
    assert resp.status_code == 200
    body = resp.json()
    assert body["graphs"] == [plugin_graphs[0]]
    assert body["skipped"] == plugin_graphs[1:]
    assert len(deleted) == 1


def test_disable_bundle_uses_grpc_assistants_when_postgres(
    _clean_lg_modules: None,
) -> None:
    # postgres backend -> route imports Assistants from langgraph_api.grpc.ops.
    plugin_graphs = list(_BUNDLE_TO_GRAPHS["plugins"])
    live_graphs = {gid: object() for gid in plugin_graphs}
    deleted: list[Any] = []
    _install_disable_stubs(graphs=live_graphs, deleted=deleted, postgres=True)

    resp = client.post("/_decepticon/bundles/plugins/disable")
    assert resp.status_code == 200
    assert resp.json()["graphs"] == plugin_graphs
    assert len(deleted) == len(plugin_graphs)
    assert live_graphs == {}


def test_disable_bundle_swallows_assistants_delete_failure(
    _clean_lg_modules: None,
) -> None:
    # A failing Assistants.delete must not abort the disable — the
    # in-memory GRAPHS removal still gates usage, DB cleanup is
    # best-effort.
    plugin_graphs = list(_BUNDLE_TO_GRAPHS["plugins"])
    live_graphs = {gid: object() for gid in plugin_graphs}
    deleted: list[Any] = []
    _install_disable_stubs(graphs=live_graphs, deleted=deleted, delete_raises=True)

    resp = client.post("/_decepticon/bundles/plugins/disable")
    assert resp.status_code == 200
    body = resp.json()
    # Graphs still reported removed despite the delete failure.
    assert body["graphs"] == plugin_graphs
    assert live_graphs == {}
