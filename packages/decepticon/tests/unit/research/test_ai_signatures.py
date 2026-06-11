"""Unit tests for the AI attack-surface signal catalogs (ADR-0007)."""

from __future__ import annotations

import pytest

from decepticon.tools.research.ai_signatures import (
    classify_ai_endpoint,
    lookup_ai_port,
    match_ai_banner,
    match_ai_headers,
    match_ai_title,
)
from decepticon_core.types.kg import TechnologyCategory, technology_key


class TestMatchAiHeaders:
    def test_header_name_signature(self) -> None:
        matches = match_ai_headers({"anthropic-version": "2023-06-01"})
        assert len(matches) == 1
        m = matches[0]
        assert m.name == "Anthropic API"
        assert m.category is TechnologyCategory.AI_RUNTIME
        assert m.confidence == "high"
        assert m.detected_by == "httpx-ai-header"

    def test_proxy_header_signature(self) -> None:
        matches = match_ai_headers({"x-litellm-version": "1.0", "X-LiteLLM-Model": "gpt-4"})
        # both headers map to LiteLLM — deduped to one match
        assert [m.name for m in matches] == ["LiteLLM"]
        assert matches[0].category is TechnologyCategory.AI_PROXY

    def test_server_value_signature(self) -> None:
        matches = match_ai_headers({"server": "vLLM/0.5.0"})
        assert matches[0].name == "vLLM"
        assert matches[0].category is TechnologyCategory.AI_RUNTIME

    def test_name_and_server_dedup(self) -> None:
        matches = match_ai_headers({"x-vllm-served-model": "x", "server": "vllm"})
        assert [m.name for m in matches] == ["vLLM"]

    def test_generic_server_no_match(self) -> None:
        assert match_ai_headers({"server": "uvicorn", "content-type": "application/json"}) == []

    def test_empty(self) -> None:
        assert match_ai_headers(None) == []
        assert match_ai_headers({}) == []


class TestLookupAiPort:
    @pytest.mark.parametrize(
        ("port", "name", "confidence"),
        [
            (11434, "Ollama", "high"),
            (6333, "Qdrant", "high"),
            (19530, "Milvus", "high"),
            (8188, "ComfyUI", "high"),
            (8000, "vLLM", "low"),
            (8080, None, None),
            (22, None, None),
        ],
    )
    def test_two_tier(self, port: int, name: str | None, confidence: str | None) -> None:
        match = lookup_ai_port(port)
        if name is None:
            assert match is None
        else:
            assert match is not None
            assert match.name == name
            assert match.confidence == confidence
            assert match.detected_by == "port-catalog"

    def test_high_port_categories(self) -> None:
        assert lookup_ai_port(11434).category is TechnologyCategory.AI_RUNTIME  # type: ignore[union-attr]
        assert lookup_ai_port(6333).category is TechnologyCategory.DATABASE  # type: ignore[union-attr]


class TestMatchAiTitle:
    @pytest.mark.parametrize(
        ("title", "name"),
        [
            ("Open WebUI", "Open WebUI"),
            ("MLflow", "MLflow"),
            ("ComfyUI - Stable Diffusion", "ComfyUI"),
            ("My Blog", None),
            ("", None),
        ],
    )
    def test_title(self, title: str, name: str | None) -> None:
        match = match_ai_title(title)
        if name is None:
            assert match is None
        else:
            assert match is not None
            assert match.name == name
            assert match.confidence == "low"
            assert match.detected_by == "title-regex"


class TestMatchAiBanner:
    def test_ollama_banner(self) -> None:
        match = match_ai_banner("Ollama", "0.1.32")
        assert match is not None
        assert match.name == "Ollama"
        assert match.confidence == "low"
        assert match.detected_by == "nmap-banner"
        assert match.version == "0.1.32"

    def test_tgi_banner(self) -> None:
        match = match_ai_banner("text-generation-inference", "")
        assert match is not None
        assert match.name == "Text Generation Inference"

    def test_no_banner(self) -> None:
        assert match_ai_banner("nginx", "1.25") is None
        assert match_ai_banner(None, None) is None


class TestClassifyAiEndpoint:
    @pytest.mark.parametrize(
        ("path", "interface"),
        [
            ("/v1/chat/completions", "chat"),
            ("/openai/deployments/gpt4/chat/completions", "chat"),
            ("/api/chat", "chat"),
            ("/v1/completions", "completion"),
            ("/api/generate", "completion"),
            ("/v1/embeddings", "embedding"),
            ("/v1/rerank", "rerank"),
            ("/v1/models", "models"),
            ("/api/tags", "models"),
            ("/v2/models/resnet/infer", "inference"),
            ("/events", "sse"),
            ("/mcp", "mcp"),
            ("/graphql", "graphql"),
            ("/about", "non-llm"),
            ("", "non-llm"),
        ],
    )
    def test_classify(self, path: str, interface: str) -> None:
        assert classify_ai_endpoint(path) == interface

    def test_trailing_slash_normalized(self) -> None:
        assert classify_ai_endpoint("/v1/models/") == "models"


def test_technology_key_roundtrip() -> None:
    # The key a port match would MERGE on is stable and category-prefixed.
    match = lookup_ai_port(11434)
    assert match is not None
    assert technology_key(match.category, match.name) == "ai-runtime:ollama"


# ── Ingest wiring (A2-A4): Technology nodes + interface tags land in the KG ──


class _FakeGraph:
    """Minimal graph backing the ``graph_transaction`` context manager."""

    def __init__(self) -> None:
        self.nodes: dict[str, object] = {}
        self.edges: dict[str, object] = {}

    def upsert_node(self, node: object) -> object:
        self.nodes[node.id] = node  # type: ignore[attr-defined]
        return node

    def upsert_edge(self, edge: object) -> object:
        self.edges[edge.id] = edge  # type: ignore[attr-defined]
        return edge

    def stats(self) -> dict[str, int]:
        return {"nodes": len(self.nodes), "edges": len(self.edges)}


def _patch_graph(monkeypatch: pytest.MonkeyPatch) -> _FakeGraph:
    graph = _FakeGraph()

    class _Tx:
        def __enter__(self) -> _FakeGraph:
            return graph

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr("decepticon.tools.research.tools.graph_transaction", lambda: _Tx())
    return graph


def _tech_nodes(graph: _FakeGraph):
    from decepticon_core.types.kg import NodeKind

    return [n for n in graph.nodes.values() if n.kind == NodeKind.TECHNOLOGY]  # type: ignore[attr-defined]


def test_httpx_ingest_promotes_technology_from_header(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from decepticon.tools.research.tools import kg_ingest_httpx_jsonl
    from decepticon_core.types.kg import EdgeKind

    graph = _patch_graph(monkeypatch)
    row = {
        "url": "https://t.example/v1/chat/completions",
        "host": "t.example",
        "port": 8000,
        "webserver": "vLLM/0.5.0",
        "title": "vLLM API",
    }
    p = tmp_path / "httpx.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = json.loads(kg_ingest_httpx_jsonl.invoke({"path": str(p)}))
    assert result["technologies"] == 1

    techs = _tech_nodes(graph)
    assert len(techs) == 1
    assert techs[0].props["key"] == "ai-runtime:vllm"
    assert techs[0].props["confidence"] == "high"
    assert techs[0].props["detected_by"] == "httpx-ai-header"
    assert any(e.kind == EdgeKind.RUNS for e in graph.edges.values())

    # A4: the entrypoint is tagged with its AI interface type.
    from decepticon_core.types.kg import NodeKind

    eps = [n for n in graph.nodes.values() if n.kind == NodeKind.ENTRYPOINT]
    assert eps[0].props["ai_interface_type"] == "chat"


def test_httpx_ingest_no_ai_signal(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from decepticon.tools.research.tools import kg_ingest_httpx_jsonl
    from decepticon_core.types.kg import NodeKind

    graph = _patch_graph(monkeypatch)
    row = {"url": "https://t.example/about", "host": "t.example", "webserver": "nginx"}
    p = tmp_path / "httpx.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = json.loads(kg_ingest_httpx_jsonl.invoke({"path": str(p)}))
    assert result["technologies"] == 0
    assert _tech_nodes(graph) == []
    eps = [n for n in graph.nodes.values() if n.kind == NodeKind.ENTRYPOINT]
    assert "ai_interface_type" not in eps[0].props


def test_masscan_promotes_high_port_only(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from decepticon.tools.research.tools import kg_ingest_masscan

    graph = _patch_graph(monkeypatch)
    entries = [
        {"ip": "10.0.0.5", "ports": [{"port": 11434, "proto": "tcp", "status": "open"}]},
        {"ip": "10.0.0.6", "ports": [{"port": 8080, "proto": "tcp", "status": "open"}]},
    ]
    p = tmp_path / "masscan.json"
    p.write_text(json.dumps(entries), encoding="utf-8")

    result = json.loads(kg_ingest_masscan.invoke({"path": str(p)}))
    assert result["technologies_added"] == 1  # 11434 (high) yes, 8080 (generic) gated

    techs = _tech_nodes(graph)
    assert [t.props["key"] for t in techs] == ["ai-runtime:ollama"]


def test_nmap_banner_and_port(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from decepticon.tools.research.tools import kg_ingest_nmap_xml

    graph = _patch_graph(monkeypatch)
    xml = """<?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="10.0.0.7" addrtype="ipv4"/>
        <ports>
          <port protocol="tcp" portid="11434">
            <state state="open"/>
            <service name="http" product="Ollama" version="0.1.32"/>
          </port>
        </ports>
      </host>
    </nmaprun>"""
    p = tmp_path / "scan.xml"
    p.write_text(xml, encoding="utf-8")

    result = json.loads(kg_ingest_nmap_xml.invoke({"path": str(p)}))
    # Port 11434 (high) and the "Ollama" banner (low) both name Ollama —
    # dedup collapses them to a single high-confidence Technology node.
    assert result["ingested"]["technologies"] == 1

    techs = _tech_nodes(graph)
    assert len(techs) == 1
    assert techs[0].props["key"] == "ai-runtime:ollama"
    assert techs[0].props["confidence"] == "high"
    assert techs[0].props["version"] == "0.1.32"


def test_katana_tags_ai_interface(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from decepticon.tools.research.tools import kg_ingest_katana
    from decepticon_core.types.kg import NodeKind

    graph = _patch_graph(monkeypatch)
    row = {"url": "https://t.example/v1/embeddings", "method": "POST"}
    p = tmp_path / "katana.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")

    kg_ingest_katana.invoke({"path": str(p)})
    urls = [n for n in graph.nodes.values() if n.kind == NodeKind.URL]
    assert urls[0].props["ai_interface_type"] == "embedding"
