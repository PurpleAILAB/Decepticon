"""Unit tests for ATT&CK Navigator layer export."""

from __future__ import annotations

import json

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research.attack.link import link_mitre
from decepticon.tools.research.attack.navigator import build_navigator_layer
from decepticon.tools.research.graph import KnowledgeGraph, Node, NodeKind


def _graph_with_findings(findings: list[dict]) -> KnowledgeGraph:
    """Build a graph from ``[{label, key, severity, detected, mitre:[...]}]``."""
    g = KnowledgeGraph()
    seen_techniques: set[str] = set()
    for spec in findings:
        for tid in spec.get("mitre", []):
            if tid not in seen_techniques:
                g.upsert_node(Node.make(NodeKind.TECHNIQUE, tid, key=tid))
                seen_techniques.add(tid)
        node = g.upsert_node(
            Node.make(
                NodeKind.FINDING,
                spec["label"],
                key=spec["key"],
                severity=spec.get("severity", "medium"),
                detected=spec.get("detected"),
            )
        )
        link_mitre(g, node, spec.get("mitre", []))
    return g


def _technique(layer: dict, tid: str) -> dict:
    return next(t for t in layer["techniques"] if t["techniqueID"] == tid)


class TestBuildNavigatorLayer:
    def test_layer_has_required_top_level_keys(self) -> None:
        layer = build_navigator_layer(KnowledgeGraph(), "Acme Q2")
        for key in ("name", "versions", "domain", "techniques", "gradient", "legendItems"):
            assert key in layer
        assert layer["domain"] == "enterprise-attack"
        assert layer["versions"]["layer"] == "4.5"

    def test_empty_graph_yields_no_techniques(self) -> None:
        layer = build_navigator_layer(KnowledgeGraph(), "Empty")
        assert layer["techniques"] == []

    def test_exercised_technique_appears(self) -> None:
        g = _graph_with_findings(
            [{"label": "SQLi", "key": "FIND-1", "severity": "high", "mitre": ["T1190"]}]
        )
        layer = build_navigator_layer(g, "Acme")
        entry = _technique(layer, "T1190")
        assert entry["enabled"] is True
        assert "FIND-1" in entry["comment"]

    def test_detected_finding_is_green(self) -> None:
        g = _graph_with_findings(
            [{"label": "x", "key": "F1", "detected": True, "mitre": ["T1190"]}]
        )
        entry = _technique(build_navigator_layer(g, "e"), "T1190")
        assert entry["color"] == "#4caf50"

    def test_undetected_finding_is_red_gap(self) -> None:
        g = _graph_with_findings(
            [{"label": "x", "key": "F1", "detected": False, "mitre": ["T1190"]}]
        )
        entry = _technique(build_navigator_layer(g, "e"), "T1190")
        assert entry["color"] == "#fc3b3b"

    def test_unknown_detection_is_grey(self) -> None:
        g = _graph_with_findings([{"label": "x", "key": "F1", "mitre": ["T1190"]}])
        entry = _technique(build_navigator_layer(g, "e"), "T1190")
        assert entry["color"] == "#b3b3b3"

    def test_score_reflects_max_severity(self) -> None:
        g = _graph_with_findings(
            [
                {"label": "a", "key": "F1", "severity": "low", "mitre": ["T1190"]},
                {"label": "b", "key": "F2", "severity": "critical", "mitre": ["T1190"]},
            ]
        )
        entry = _technique(build_navigator_layer(g, "e"), "T1190")
        assert entry["score"] == 4

    def test_detected_wins_over_gap_when_mixed(self) -> None:
        g = _graph_with_findings(
            [
                {"label": "a", "key": "F1", "detected": False, "mitre": ["T1190"]},
                {"label": "b", "key": "F2", "detected": True, "mitre": ["T1190"]},
            ]
        )
        entry = _technique(build_navigator_layer(g, "e"), "T1190")
        assert entry["color"] == "#4caf50"


class TestExportAttackNavigatorTool:
    def test_tool_returns_writable_layer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.reporting.tools import export_attack_navigator

        class _FakeStore:
            def __init__(self, graph: KnowledgeGraph) -> None:
                self.graph = graph

            def load_graph(self):
                return self.graph.model_copy(deep=True)

        g = _graph_with_findings(
            [{"label": "SQLi", "key": "FIND-1", "severity": "high", "mitre": ["T1190"]}]
        )
        monkeypatch.setattr(state, "_store", _FakeStore(g))
        payload = json.loads(export_attack_navigator.invoke({"engagement_name": "Acme"}))
        assert payload["domain"] == "enterprise-attack"
        assert any(t["techniqueID"] == "T1190" for t in payload["techniques"])
