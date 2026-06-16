"""Tests for decepticon.mcp_server.findings (KG -> summary/SARIF)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from decepticon.mcp_server.findings import (
    engagement_workspace,
    load_findings_graph,
    summarize_findings,
)


class _Node:
    """Duck-typed KnowledgeGraph node (matches the shape sarif_export reads)."""

    def __init__(self, node_id: str, kind: str, label: str, props: dict[str, Any]) -> None:
        self.id = node_id
        self.kind = kind
        self.label = label
        self.properties = props


class _Graph:
    def __init__(self, nodes: list[_Node]) -> None:
        self.nodes = {n.id: n for n in nodes}


def test_summarize_absent_graph_is_unavailable() -> None:
    result = summarize_findings(None, engagement_name="eng", include_sarif=False)
    assert result.available is False
    assert result.result_count == 0
    assert result.level_counts == {}
    assert result.sarif is None


def test_summarize_high_finding_counts_error_level() -> None:
    graph = _Graph([_Node("f1", "finding", "f1", {"severity": "high", "vuln_class": "sqli"})])
    result = summarize_findings(graph, engagement_name="eng", include_sarif=False)
    assert result.available is True
    assert result.result_count == 1
    assert result.level_counts.get("error") == 1
    assert result.sarif is None


def test_summarize_include_sarif_attaches_document() -> None:
    graph = _Graph([_Node("f1", "finding", "f1", {"severity": "high"})])
    result = summarize_findings(graph, engagement_name="eng", include_sarif=True)
    assert result.sarif is not None
    assert result.sarif["version"] == "2.1.0"


def test_engagement_workspace_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    assert engagement_workspace("anything") == tmp_path


def test_load_findings_graph_absent_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    assert load_findings_graph("eng") is None


# ── path-traversal hardening (engagement_name is remote MCP input) ──────────
# A malicious engagement name must never resolve outside the workspace root.
# pathlib drops the left operand of ``/`` when the right side is absolute, and
# treats ``..`` as a real parent step, so an unvalidated name is an arbitrary
# file read + existence oracle on the bridge host.
_UNSAFE_NAMES = [
    "../../../../etc/ssl",
    "/root/.ssh",
    "a/b",
    "..",
    "",
    "with space",
    "x" * 200,
    "name\x00.json",
]


@pytest.mark.parametrize("bad_name", _UNSAFE_NAMES)
def test_engagement_workspace_rejects_unsafe_names(bad_name: str) -> None:
    with pytest.raises(ValueError):
        engagement_workspace(bad_name)


@pytest.mark.parametrize("bad_name", _UNSAFE_NAMES)
def test_load_findings_graph_rejects_unsafe_names(bad_name: str) -> None:
    # Treated as "no findings" rather than reading an attacker-chosen path.
    # No env override is set, so a valid name would resolve under $HOME; the
    # unsafe names must short-circuit to None before any filesystem access.
    assert load_findings_graph(bad_name) is None
