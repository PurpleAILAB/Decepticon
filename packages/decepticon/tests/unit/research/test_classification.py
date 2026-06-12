"""Unit tests for JS endpoint + parameter classification taxonomy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from decepticon.tools.research.chain import Chain, ChainStep, critical_path_score
from decepticon.tools.research.classification import (
    classify_endpoint,
    classify_endpoints,
    classify_parameter,
    infer_parameter_type,
)
from decepticon.tools.research.tools import kg_ingest_ffuf, kg_ingest_katana
from decepticon_core.types.kg import Edge, Node, NodeKind


def test_classify_parameter() -> None:
    assert classify_parameter("id") == "id_params"
    assert classify_parameter("user_id") == "id_params"
    assert classify_parameter("some_other_id") == "id_params"
    assert classify_parameter("some_other_Id") == "id_params"
    assert classify_parameter("file") == "file_params"
    assert classify_parameter("filepath") == "file_params"
    assert classify_parameter("q") == "search_params"
    assert classify_parameter("query") == "search_params"
    assert classify_parameter("username") == "auth_params"
    assert classify_parameter("token") == "auth_params"
    assert classify_parameter("redirect") == "redirect_params"
    assert classify_parameter("returnurl") == "redirect_params"
    assert classify_parameter("cmd") == "command_params"
    assert classify_parameter("shell") == "command_params"
    assert classify_parameter("unknown_param") == "other"


def test_infer_parameter_type() -> None:
    assert infer_parameter_type("id", ["123", "-45"]) == "integer"
    assert infer_parameter_type("file", ["/etc/passwd"]) == "path"
    assert infer_parameter_type("email", ["test@example.com"]) == "email"
    assert infer_parameter_type("url", ["https://google.com"]) == "url"
    assert infer_parameter_type("flag", ["true", "false"]) == "boolean"
    assert infer_parameter_type("name", ["alice"]) == "string"


def test_classify_endpoint() -> None:
    assert classify_endpoint("/login", ["POST"], {"query": [], "body": []}) == "authentication"
    assert classify_endpoint("/admin/dashboard", ["GET"], {"query": [], "body": []}) == "admin"
    assert classify_endpoint("/api/v1/users", ["GET"], {"query": [], "body": []}) == "api"
    assert classify_endpoint("/download/pdf", ["GET"], {"query": [], "body": []}) == "file_access"
    assert classify_endpoint("/upload/avatar", ["POST"], {"query": [], "body": []}) == "upload"
    assert classify_endpoint("/search/products", ["GET"], {"query": [], "body": []}) == "search"
    assert classify_endpoint("/index.html", ["GET"], {"query": [], "body": []}) == "static"
    assert classify_endpoint("/page.php", ["GET"], {"query": [], "body": []}) == "dynamic"


def test_classify_endpoints_tool() -> None:
    urls = [
        "https://example.com/api/v1/users?id=123",
        "https://example.com/download?file=/etc/passwd",
        "https://example.com/search?q=test&page=2",
    ]
    res_str = classify_endpoints.invoke({"urls": urls})
    res = json.loads(res_str)

    assert "https://example.com/api/v1/users?id=123" in res
    item1 = res["https://example.com/api/v1/users?id=123"]
    assert item1["category"] == "api"
    assert "id" in item1["parameters"]
    assert "id_params" in item1["parameter_categories"]

    assert "https://example.com/download?file=/etc/passwd" in res
    item2 = res["https://example.com/download?file=/etc/passwd"]
    assert item2["category"] == "file_access"
    assert "file_params" in item2["parameter_categories"]


class FakeStore:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self.stats_dict: dict[str, int] = {}

    def upsert_node(self, node: Node) -> Node:
        self.nodes[node.id] = node
        return node

    def upsert_edge(self, edge: Edge) -> Edge:
        self.edges[edge.id] = edge
        return edge

    def stats(self) -> dict[str, int]:
        return {"nodes": len(self.nodes), "edges": len(self.edges)}

    def query_custom(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # Mock behavior for testing critical_path_score
        res = []
        ids = params.get("ids", [])
        for nid in ids:
            if nid in self.nodes:
                node = self.nodes[nid]
                res.append(
                    {
                        "param_classes": node.props.get("param_classes", []),
                        "category": node.props.get("endpoint_category", ""),
                    }
                )
        return res


def test_kg_ingest_katana_with_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeStore()
    monkeypatch.setattr("decepticon.tools.research._state.get_store", lambda: fake)
    monkeypatch.setattr(
        "decepticon.tools.research._state.graph_transaction", lambda: pytest.raises(RuntimeError)
    )  # not needed

    class Transaction:
        def __enter__(self):
            return fake

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("decepticon.tools.research.tools.graph_transaction", lambda: Transaction())

    p = tmp_path / "katana.jsonl"
    row = {
        "url": "https://example.com/api/v1/run?cmd=whoami",
        "method": "POST",
    }
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = json.loads(kg_ingest_katana.invoke({"path": str(p)}))
    assert result["urls_added"] == 1

    url_nodes = [n for n in fake.nodes.values() if n.kind == NodeKind.URL]
    assert len(url_nodes) == 1
    node = url_nodes[0]
    assert node.props["endpoint_category"] == "api"
    assert "command_params" in node.props["param_classes"]
    assert "cmd" in node.props["params"]


def test_kg_ingest_ffuf_with_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeStore()

    class Transaction:
        def __enter__(self):
            return fake

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("decepticon.tools.research.tools.graph_transaction", lambda: Transaction())

    p = tmp_path / "ffuf.json"
    data = {
        "results": [
            {
                "url": "https://example.com/download?file=abc.txt",
                "status": 200,
                "length": 100,
            }
        ]
    }
    p.write_text(json.dumps(data), encoding="utf-8")

    result = json.loads(kg_ingest_ffuf.invoke({"path": str(p)}))
    assert result["urls_added"] == 1

    url_nodes = [n for n in fake.nodes.values() if n.kind == NodeKind.URL]
    assert len(url_nodes) == 1
    node = url_nodes[0]
    assert node.props["endpoint_category"] == "file_access"
    assert "file_params" in node.props["param_classes"]


def test_critical_path_score_boost_with_command_params(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeStore()
    monkeypatch.setattr("decepticon.tools.research.chain.get_store", lambda: fake)

    ep = Node.make(
        NodeKind.ENTRYPOINT,
        "https://example.com/run",
        key="ep-key",
        param_classes=["command_params"],
    )
    fake.nodes[ep.id] = ep

    chain = Chain(
        entrypoint_id=ep.id,
        entrypoint_label=ep.label,
        crown_jewel_id="goal-id",
        crown_jewel_label="crown",
        total_cost=10.0,
        steps=[
            ChainStep(
                node_id=ep.id,
                node_label=ep.label,
                node_kind="Entrypoint",
                edge_kind="EXPOSES",
                hop_cost=1.0,
            )
        ],
    )

    score_with_boost = critical_path_score(chain)

    # Score without boost (empty param_classes)
    ep_noboost = Node.make(
        NodeKind.ENTRYPOINT,
        "https://example.com/run",
        key="ep-key",
        param_classes=[],
    )
    fake.nodes[ep.id] = ep_noboost
    score_without_boost = critical_path_score(chain)

    assert score_with_boost > score_without_boost
    assert score_with_boost - score_without_boost == 5.0
