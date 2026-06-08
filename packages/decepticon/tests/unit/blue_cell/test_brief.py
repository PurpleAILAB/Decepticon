"""Tests for the Defense Brief deliverable (tools/defense/brief.py).

Exercises the coverage math, MTTD stats, detected/gap technique split, the
ATT&CK Navigator layer, and both @tools over an in-memory graph. No Neo4j.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.defense.brief import (
    _percentile,
    build_defense_brief,
    build_navigator_layer,
    defense_brief,
    export_attack_navigator,
    render_brief_markdown,
)
from decepticon.tools.research import _state as state
from decepticon_core.types.kg import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind


def _seed(graph: KnowledgeGraph) -> None:
    """2 detected findings (fast + slow) + 1 gap + 1 deployed rule."""
    kerb = graph.upsert_node(
        Node.make(
            NodeKind.FINDING, "Kerberoast SPN", key="F1", technique="T1558.003", severity="high"
        )
    )
    fired_fast = graph.upsert_node(
        Node.make(
            NodeKind.DETECTION_FIRED,
            "Kerberoast",
            key="d::1",
            rule_id="DCEP-T1558.003-kerberoast",
            mitre=["T1558.003"],
            mttd_seconds=1.2,
            event_ts=100.0,
        )
    )
    graph.upsert_edge(Edge.make(fired_fast.id, kerb.id, EdgeKind.DETECTED))

    dcsync = graph.upsert_node(
        Node.make(NodeKind.FINDING, "DCSync", key="F3", technique="T1003.006", severity="critical")
    )
    fired_slow = graph.upsert_node(
        Node.make(
            NodeKind.DETECTION_FIRED,
            "DCSync",
            key="d::2",
            rule_id="DCEP-T1003.006-dcsync",
            mitre=["T1003.006"],
            mttd_seconds=12.0,
            event_ts=200.0,
        )
    )
    graph.upsert_edge(Edge.make(fired_slow.id, dcsync.id, EdgeKind.DETECTED))

    # Gap: ran but nothing detected it.
    graph.upsert_node(
        Node.make(
            NodeKind.FINDING, "DLL side-load", key="F2", technique="T1574.002", severity="medium"
        )
    )
    # A rule the Defender deployed.
    graph.upsert_node(
        Node.make(
            NodeKind.DEFENSE_ACTION,
            "DCSync rule",
            key="rule::DCEP-T1003.006-dcsync",
            rule_id="DCEP-T1003.006-dcsync",
            mitre=["T1003.006"],
            siem_target="sentinel",
            status="deployed",
        )
    )


# ── coverage math ──────────────────────────────────────────────────────────


def test_coverage_counts_and_percentage() -> None:
    graph = KnowledgeGraph()
    _seed(graph)
    cov = build_defense_brief(graph)["coverage"]
    assert cov == {
        "findings_observed": 3,
        "findings_detected": 2,
        "findings_missed": 1,
        "detected_pct": 66.7,
    }


def test_detected_techniques_sorted_slowest_first() -> None:
    brief = build_defense_brief(_seeded_graph())
    assert [d["technique"] for d in brief["detected_techniques"]] == ["T1003.006", "T1558.003"]
    assert brief["mttd"]["median_seconds"] == 6.6
    assert brief["mttd"]["max_seconds"] == 12.0


def test_gaps_and_deployed_inventory() -> None:
    brief = build_defense_brief(_seeded_graph())
    assert brief["missed_techniques"] == ["T1574.002"]
    assert [g["finding"] for g in brief["detection_gaps"]] == ["DLL side-load"]
    assert brief["deployed_rules"][0]["siem_target"] == "sentinel"


# ── navigator layer ─────────────────────────────────────────────────────────


def test_navigator_layer_colours_detected_and_gaps() -> None:
    layer = build_navigator_layer(build_defense_brief(_seeded_graph()))
    assert layer["domain"] == "enterprise-attack"
    by_id = {t["techniqueID"]: t for t in layer["techniques"]}
    assert by_id["T1003.006"]["score"] == 100 and by_id["T1003.006"]["color"] == "#2ecc71"
    assert by_id["T1574.002"]["score"] == 0 and by_id["T1574.002"]["color"] == "#e74c3c"


def test_markdown_contains_headline_numbers() -> None:
    md = render_brief_markdown(build_defense_brief(_seeded_graph(), engagement_name="ACME"))
    assert "Engagement: ACME" in md
    assert "2 detected (66.7%)" in md
    assert "T1003.006 — fired in 12.0s" in md
    assert "DLL side-load" in md


def test_percentile_interpolates() -> None:
    assert _percentile([], 0.95) == 0.0
    assert _percentile([5.0], 0.95) == 5.0
    assert _percentile([0.0, 10.0], 0.5) == 5.0


# ── @tools over the store ────────────────────────────────────────────────────


class _FakeStore:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def load_graph(self) -> KnowledgeGraph:
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes) -> int:
        for n in nodes:
            self.graph.upsert_node(n)
        return 0

    def batch_upsert_edges(self, edges) -> int:
        for e in edges:
            self.graph.upsert_edge(e)
        return 0


def test_defense_brief_tool_returns_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStore()
    _seed(fake.graph)
    monkeypatch.setattr(state, "_store", fake)
    result = json.loads(defense_brief.invoke({"engagement_name": "ACME"}))
    assert result["coverage"]["detected_pct"] == 66.7
    assert "Engagement: ACME" in result["markdown"]


def test_export_navigator_tool_writes_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeStore()
    _seed(fake.graph)
    monkeypatch.setattr(state, "_store", fake)
    out = tmp_path / "nav" / "layer.json"
    summary = json.loads(export_attack_navigator.invoke({"output_path": str(out)}))
    assert summary["techniques"] == 3
    layer = json.loads(out.read_text(encoding="utf-8"))
    assert {t["techniqueID"] for t in layer["techniques"]} == {
        "T1003.006",
        "T1558.003",
        "T1574.002",
    }


def _seeded_graph() -> KnowledgeGraph:
    graph = KnowledgeGraph()
    _seed(graph)
    return graph
