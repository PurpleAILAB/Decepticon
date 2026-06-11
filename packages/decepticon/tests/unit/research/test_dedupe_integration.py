"""End-to-end tests for auto-deduplication on node insertion and active
finding validation (false-positive reduction).

Covers:
- ``dedupe.deterministic_judge`` / ``merge_nodes`` / ``integrate_node`` — the
  LLM-free write-path dedup pipeline.
- ``tools.kg_add_node`` — auto-merge of semantic duplicates through the tool.
- ``validate.run_active_validation`` / ``validate_finding`` — probing a
  finding node and flipping ``validated`` / ``false-positive``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research import tools as research_tools
from decepticon.tools.research.dedupe import (
    deterministic_judge,
    integrate_node,
    merge_nodes,
)
from decepticon.tools.research.validate import (
    _XSS_PAYLOAD,
    CHECK_KEY_ACCEPTED,
    CHECK_MISSING,
    CHECK_REFLECTED_XSS,
    CHECK_UNPROBEABLE,
    derive_probe,
    run_active_validation,
)
from decepticon_core.types.kg import KnowledgeGraph, Node, NodeKind

# ── Fakes ───────────────────────────────────────────────────────────────


class _FakeStore:
    """In-memory KGStore-shaped fake (mirrors test_dedupe / test_tools)."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def load_graph(self) -> KnowledgeGraph:
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes: list[Node]) -> int:
        for n in nodes:
            self.graph.upsert_node(n)
        return len(nodes)

    def batch_upsert_edges(self, edges: list[Any]) -> int:
        for e in edges:
            self.graph.upsert_edge(e)
        return len(edges)

    def ensure_schema(self) -> None:
        pass

    def close(self) -> None:
        pass

    def stats(self) -> dict[str, int]:
        return self.graph.stats()


def _configure_store(monkeypatch: pytest.MonkeyPatch, graph: KnowledgeGraph) -> _FakeStore:
    fake = _FakeStore(graph)
    monkeypatch.setattr(state, "_store", fake)
    return fake


def _vuln(label: str, **props: Any) -> Node:
    props.setdefault("key", f"vuln::{label}")
    return Node.make(NodeKind.VULNERABILITY, label, **props)


def _sqli(label: str, *, host: str = "api.example.com", severity: str = "high", **extra: Any) -> Node:
    return _vuln(label, host=host, cwe=["CWE-89"], severity=severity, **extra)


# ── deterministic_judge ─────────────────────────────────────────────────


class TestDeterministicJudge:
    def test_same_endpoint_compatible_cwe_is_duplicate(self) -> None:
        a = Node.make(NodeKind.FINDING, "A", key="a", url="https://x.io/api/orders/1?t=1")
        b = Node.make(NodeKind.FINDING, "B", key="b", url="http://x.io/api/orders/1?t=2")
        assert deterministic_judge(a, b)["is_duplicate"] is True

    def test_conflicting_cwe_classes_not_duplicate(self) -> None:
        # Same endpoint but XSS vs SQLi → genuinely different bugs.
        a = Node.make(NodeKind.VULNERABILITY, "XSS", key="a", url="https://x.io/s", cwe=["CWE-79"])
        b = Node.make(NodeKind.VULNERABILITY, "SQLi", key="b", url="https://x.io/s", cwe=["CWE-89"])
        verdict = deterministic_judge(a, b)
        assert verdict["is_duplicate"] is False
        assert "CWE" in verdict["reason"]

    def test_shared_cwe_same_host_is_duplicate(self) -> None:
        assert deterministic_judge(_sqli("A"), _sqli("B"))["is_duplicate"] is True

    def test_same_host_only_is_not_duplicate(self) -> None:
        # No endpoint, no CWE overlap — host alone is too weak to merge.
        a = _vuln("Open redirect", host="api.example.com")
        b = _vuln("Verbose error page", host="api.example.com")
        assert deterministic_judge(a, b)["is_duplicate"] is False


# ── merge_nodes ─────────────────────────────────────────────────────────


class TestMergeNodes:
    def test_keeps_higher_severity(self) -> None:
        canonical = _sqli("A", severity="low")
        merge_nodes(canonical, _sqli("B", severity="critical"))
        assert canonical.props["severity"] == "critical"

    def test_does_not_downgrade_severity(self) -> None:
        canonical = _sqli("A", severity="critical")
        merge_nodes(canonical, _sqli("B", severity="low"))
        assert canonical.props["severity"] == "critical"

    def test_keeps_longer_description(self) -> None:
        canonical = _sqli("A", description="short")
        merge_nodes(canonical, _sqli("B", description="a much longer and more detailed writeup"))
        assert canonical.props["description"] == "a much longer and more detailed writeup"

    def test_validated_is_sticky_from_candidate(self) -> None:
        canonical = _sqli("A")  # no validated flag
        merge_nodes(canonical, _sqli("B", validated=True))
        assert canonical.props["validated"] is True

    def test_validated_is_sticky_from_canonical(self) -> None:
        canonical = _sqli("A", validated=True)
        merge_nodes(canonical, _sqli("B", validated=False))
        assert canonical.props["validated"] is True

    def test_validated_clears_false_positive(self) -> None:
        canonical = _sqli("A", **{"false-positive": True})
        merge_nodes(canonical, _sqli("B", validated=True))
        assert canonical.props["validated"] is True
        assert canonical.props["false-positive"] is False

    def test_fills_missing_props_without_clobbering(self) -> None:
        canonical = _sqli("A", file="app.py")
        merge_nodes(canonical, _sqli("B", file="other.py", line=42))
        # existing non-empty value preserved, missing key filled
        assert canonical.props["file"] == "app.py"
        assert canonical.props["line"] == 42


# ── integrate_node ──────────────────────────────────────────────────────


class TestIntegrateNode:
    def test_merges_duplicate_without_creating_node(self) -> None:
        graph = KnowledgeGraph()
        first = graph.upsert_node(_sqli("SQL injection in login", severity="high"))
        node, merged = integrate_node(
            graph, _sqli("DB injection via auth endpoint", severity="critical")
        )
        assert merged is True
        assert node.id == first.id
        assert len(graph.by_kind(NodeKind.VULNERABILITY)) == 1
        assert graph.nodes[first.id].props["severity"] == "critical"

    def test_distinct_findings_create_separate_nodes(self) -> None:
        graph = KnowledgeGraph()
        graph.upsert_node(_sqli("SQLi", host="api.example.com"))
        node, merged = integrate_node(
            graph,
            _vuln("Reflected XSS", host="shop.other.net", cwe=["CWE-79"], severity="medium"),
        )
        assert merged is False
        assert len(graph.by_kind(NodeKind.VULNERABILITY)) == 2

    def test_non_finding_kind_inserts_normally(self) -> None:
        graph = KnowledgeGraph()
        node, merged = integrate_node(graph, Node.make(NodeKind.HOST, "10.0.0.1"))
        assert merged is False
        assert node.id in graph.nodes

    def test_exact_id_match_upserts_without_semantic_merge(self) -> None:
        graph = KnowledgeGraph()
        first = graph.upsert_node(_sqli("dup", severity="low"))
        node, merged = integrate_node(graph, _sqli("dup", severity="high"))
        # same (kind, key) → same id → ordinary id-dedup, not a semantic merge
        assert merged is False
        assert node.id == first.id
        assert graph.nodes[first.id].props["severity"] == "high"


# ── kg_add_node tool (end-to-end through the store) ─────────────────────


class TestKgAddNodeAutoDedup:
    def test_tool_merges_semantic_duplicate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_store(monkeypatch, KnowledgeGraph())
        first = json.loads(
            research_tools.kg_add_node.invoke(
                {
                    "kind": "Vulnerability",
                    "label": "SQL injection in login form",
                    "props": json.dumps(
                        {"host": "api.example.com", "cwe": ["CWE-89"], "severity": "high"}
                    ),
                }
            )
        )
        second = json.loads(
            research_tools.kg_add_node.invoke(
                {
                    "kind": "Vulnerability",
                    "label": "Database injection via auth endpoint",
                    "props": json.dumps(
                        {"host": "https://API.example.com:443/login", "cwe": ["CWE-89"],
                         "severity": "critical"}
                    ),
                }
            )
        )
        assert second.get("deduplicated") is True
        assert second["canonical_id"] == first["id"]
        vulns = fake.graph.by_kind(NodeKind.VULNERABILITY)
        assert len(vulns) == 1
        assert vulns[0].props["severity"] == "critical"

    def test_tool_keeps_distinct_findings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_store(monkeypatch, KnowledgeGraph())
        research_tools.kg_add_node.invoke(
            {"kind": "Vulnerability", "label": "high", "props": '{"severity": "high"}'}
        )
        research_tools.kg_add_node.invoke(
            {"kind": "Vulnerability", "label": "low", "props": '{"severity": "low"}'}
        )
        assert len(fake.graph.by_kind(NodeKind.VULNERABILITY)) == 2


# ── derive_probe ────────────────────────────────────────────────────────


class TestDeriveProbe:
    def test_no_target_returns_none(self) -> None:
        assert derive_probe(_vuln("XSS somewhere")) is None

    def test_xss_probe_shape(self) -> None:
        node = _vuln("Reflected XSS in search", url="https://t.io/s", cwe=["CWE-79"])
        spec = derive_probe(node)
        assert spec is not None
        assert spec.check == CHECK_REFLECTED_XSS
        assert _XSS_PAYLOAD in spec.success_patterns
        assert spec.negative_command is not None

    def test_key_probe_shape(self) -> None:
        node = _vuln("API key accepted", url="https://t.io/api", cwe=["CWE-287"], key_value="k1")
        spec = derive_probe(node)
        assert spec is not None
        assert spec.check == CHECK_KEY_ACCEPTED
        assert "k1" in spec.command


# ── run_active_validation (stub runner, no sandbox) ─────────────────────


def _runner(responses: dict[str, tuple[str, str, int]], default: tuple[str, str, int]):
    """Build a PoCRunner that picks a response by command substring."""

    async def _run(command: str) -> tuple[str, str, int]:
        for needle, resp in responses.items():
            if needle in command:
                return resp
        return default

    return _run


def _xss_finding() -> tuple[KnowledgeGraph, str]:
    graph = KnowledgeGraph()
    node = graph.upsert_node(
        _vuln("Reflected XSS in search", url="https://t.io/search", cwe=["CWE-79"])
    )
    return graph, node.id


class TestRunActiveValidation:
    @pytest.mark.asyncio
    async def test_xss_reflected_validates(self) -> None:
        graph, fid = _xss_finding()
        runner = _runner(
            {
                "data-urlencode": (f"HTTP/1.1 200 OK\r\n\r\n<html>{_XSS_PAYLOAD}</html>", "", 0),
            },
            default=("HTTP/1.1 200 OK\r\n\r\n<html>clean</html>", "", 0),
        )
        result = await run_active_validation(finding_id=fid, graph=graph, runner=runner)
        assert result.validated is True
        assert result.false_positive is False
        assert graph.nodes[fid].props["validated"] is True
        assert graph.nodes[fid].props["false-positive"] is False

    @pytest.mark.asyncio
    async def test_xss_static_reflection_demoted(self) -> None:
        graph, fid = _xss_finding()
        # Marker appears even WITHOUT the injected param → static content.
        static_page = f"HTTP/1.1 200 OK\r\n\r\n<html>{_XSS_PAYLOAD}</html>"
        runner = _runner({}, default=(static_page, "", 0))
        result = await run_active_validation(finding_id=fid, graph=graph, runner=runner)
        assert result.validated is False
        assert graph.nodes[fid].props["false-positive"] is True

    @pytest.mark.asyncio
    async def test_key_accepted_validates(self) -> None:
        graph = KnowledgeGraph()
        node = graph.upsert_node(
            _vuln("API key accepted without scope", url="https://t.io/api", cwe=["CWE-287"],
                  key_value="leaked-key")
        )
        runner = _runner(
            {"Authorization": ("200", "", 0)},
            default=("401", "", 0),  # without the key → unauthorized
        )
        result = await run_active_validation(finding_id=node.id, graph=graph, runner=runner)
        assert result.validated is True
        assert graph.nodes[node.id].props["validated"] is True

    @pytest.mark.asyncio
    async def test_key_open_endpoint_demoted(self) -> None:
        graph = KnowledgeGraph()
        node = graph.upsert_node(
            _vuln("API key accepted", url="https://t.io/api", cwe=["CWE-287"], key_value="k")
        )
        # Endpoint returns 200 regardless of the key → acceptance unproven.
        runner = _runner({}, default=("200", "", 0))
        result = await run_active_validation(finding_id=node.id, graph=graph, runner=runner)
        assert result.validated is False
        assert graph.nodes[node.id].props["false-positive"] is True

    @pytest.mark.asyncio
    async def test_refused_probe_marks_false_positive(self) -> None:
        graph, fid = _xss_finding()
        runner = _runner({}, default=("", "[SANDBOX_ERROR] RuntimeError: blocked", -1))
        result = await run_active_validation(finding_id=fid, graph=graph, runner=runner)
        assert result.refused is True
        assert result.validated is False
        assert graph.nodes[fid].props["false-positive"] is True

    @pytest.mark.asyncio
    async def test_missing_node_no_mutation(self) -> None:
        graph = KnowledgeGraph()
        runner = _runner({}, default=("200", "", 0))
        result = await run_active_validation(finding_id="deadbeef", graph=graph, runner=runner)
        assert result.check == CHECK_MISSING
        assert result.validated is False
        assert result.false_positive is False

    @pytest.mark.asyncio
    async def test_unprobeable_node_no_mutation(self) -> None:
        graph = KnowledgeGraph()
        node = graph.upsert_node(_vuln("XSS with no target"))
        runner = _runner({}, default=("200", "", 0))
        result = await run_active_validation(finding_id=node.id, graph=graph, runner=runner)
        assert result.check == CHECK_UNPROBEABLE
        assert "validated" not in graph.nodes[node.id].props


# ── validate_finding tool wiring ────────────────────────────────────────


class _FakeSandbox:
    """Minimal HTTPSandbox stand-in: routes commands to canned curl output."""

    def __init__(self, responses: dict[str, str], default: str) -> None:
        self.responses = responses
        self.default = default

    async def execute_tmux_async(self, *, command: str, session: str, timeout: int, is_input: bool):
        for needle, out in self.responses.items():
            if needle in command:
                return out
        return self.default


def _install_get_sandbox(monkeypatch: pytest.MonkeyPatch, sandbox: Any) -> None:
    """Stub the lazily-imported ``decepticon.tools.bash.bash.get_sandbox``.

    ``bash.bash`` has a cold-import cycle (its deps import the partially
    initialized ``decepticon.tools.bash`` package), so we register a stub
    submodule in ``sys.modules`` rather than importing the real one. The
    tool resolves ``get_sandbox`` from this stub at call time.
    """
    import sys
    import types

    import decepticon.tools as tools_pkg

    pkg = sys.modules.get("decepticon.tools.bash") or types.ModuleType("decepticon.tools.bash")
    sub = sys.modules.get("decepticon.tools.bash.bash") or types.ModuleType(
        "decepticon.tools.bash.bash"
    )
    monkeypatch.setattr(sub, "get_sandbox", lambda: sandbox, raising=False)
    monkeypatch.setattr(pkg, "bash", sub, raising=False)
    monkeypatch.setitem(sys.modules, "decepticon.tools.bash", pkg)
    monkeypatch.setitem(sys.modules, "decepticon.tools.bash.bash", sub)
    monkeypatch.setattr(tools_pkg, "bash", pkg, raising=False)


class TestValidateFindingTool:
    def test_registered_under_kg_name(self) -> None:
        names = {getattr(t, "name", None) for t in research_tools.RESEARCH_TOOLS}
        assert "kg_validate_finding" in names

    @pytest.mark.asyncio
    async def test_returns_error_without_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_get_sandbox(monkeypatch, None)
        out = json.loads(await research_tools.kg_validate_finding.ainvoke({"finding_id": "x"}))
        assert "error" in out

    @pytest.mark.asyncio
    async def test_tool_validates_via_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        graph = KnowledgeGraph()
        node = graph.upsert_node(
            _vuln("Reflected XSS in q", url="https://t.io/search", cwe=["CWE-79"])
        )
        fake = _configure_store(monkeypatch, graph)
        sandbox = _FakeSandbox(
            {"data-urlencode": f"HTTP/1.1 200 OK\r\n\r\n{_XSS_PAYLOAD}\n[Exit code: 0]"},
            default="HTTP/1.1 200 OK\r\n\r\nclean\n[Exit code: 0]",
        )
        _install_get_sandbox(monkeypatch, sandbox)
        out = json.loads(
            await research_tools.kg_validate_finding.ainvoke({"finding_id": node.id})
        )
        assert out["validated"] is True
        assert fake.graph.nodes[node.id].props["validated"] is True

