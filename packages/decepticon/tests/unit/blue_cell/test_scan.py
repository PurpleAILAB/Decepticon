"""Tests for the blue_cell_scan detection-coverage tool.

Exercises the real BlueCellTap + RuleMatcher against the bundled ruleset and
asserts the knowledge-graph effects that close the Offensive Vaccine loop:
DetectionFired/DefenseAction nodes, USES_RULE/DETECTED edges, the detection-gap
list, and idempotent write-once MTTD on re-scan. No Neo4j, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.blue_cell.rule_match import DetectionEvent, DetectionRule
from decepticon.tools.defense.blue_cell import _record_hit, _scan_and_record, blue_cell_scan
from decepticon.tools.research import _state as state
from decepticon_core.types.kg import EdgeKind, KnowledgeGraph, Node, NodeKind

_KERBEROAST = "$ GetUserSPNs.py -request -dc-ip 10.0.0.1 corp.local/svc"
_DCSYNC = "$ secretsdump.py -just-dc corp.local/admin@10.0.0.1"


def _workspace_with(tmp_path: Path, *lines: str) -> str:
    sessions = tmp_path / ".sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "main.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(tmp_path)


def _scan(graph: KnowledgeGraph, tmp_path: Path, *lines: str, now_ts: float = 1_000.0) -> dict:
    workspace = _workspace_with(tmp_path, *lines)
    return _scan_and_record(graph, workspace_path=workspace, rules_path="", now_ts=now_ts)


# ── recording ────────────────────────────────────────────────────────────


def test_scan_records_detection_fired_and_uses_rule(tmp_path: Path) -> None:
    graph = KnowledgeGraph()
    summary = _scan(graph, tmp_path, _KERBEROAST)

    fired = graph.by_kind(NodeKind.DETECTION_FIRED)
    actions = graph.by_kind(NodeKind.DEFENSE_ACTION)
    assert len(fired) == 1
    assert len(actions) == 1
    assert fired[0].props["rule_id"] == "DCEP-T1558.003-kerberoast"
    assert fired[0].props["mitre"] == ["T1558.003"]
    assert fired[0].props["source"] == "sandbox.tmux.main"
    # DetectionFired -[:USES_RULE]-> DefenseAction
    rule_edges = graph.neighbors(fired[0].id, edge_kind=EdgeKind.USES_RULE)
    assert [n.id for _, n in rule_edges] == [actions[0].id]
    assert summary["detections"] == 1
    assert "T1558.003" in summary["techniques_detected"]
    assert summary["rules_loaded"] == 10  # bundled baseline ruleset


def test_scan_fires_multiple_rules_across_events(tmp_path: Path) -> None:
    graph = KnowledgeGraph()
    summary = _scan(graph, tmp_path, _KERBEROAST, _DCSYNC)
    assert summary["detections"] == 2
    assert set(summary["techniques_detected"]) == {"T1558.003", "T1003.006"}


# ── attribution + gaps ─────────────────────────────────────────────────────


def test_scan_links_detected_to_matching_finding_and_reports_gaps(tmp_path: Path) -> None:
    graph = KnowledgeGraph()
    caught = graph.upsert_node(
        Node.make(NodeKind.FINDING, "Kerberoastable SPN", key="FIND-1", technique="T1558.003")
    )
    graph.upsert_node(Node.make(NodeKind.FINDING, "Open redirect", key="FIND-2"))

    summary = _scan(graph, tmp_path, _KERBEROAST)

    fired = graph.by_kind(NodeKind.DETECTION_FIRED)[0]
    detected = graph.neighbors(fired.id, edge_kind=EdgeKind.DETECTED)
    assert [n.id for _, n in detected] == [caught.id]
    assert summary["findings_total"] == 2
    assert summary["findings_detected"] == 1
    assert summary["detection_gaps"] == ["Open redirect"]


def test_scan_empty_workspace_reports_zero_but_still_lists_gaps(tmp_path: Path) -> None:
    graph = KnowledgeGraph()
    graph.upsert_node(Node.make(NodeKind.FINDING, "Undetected RCE", key="FIND-1"))
    summary = _scan_and_record(graph, workspace_path=str(tmp_path), rules_path="", now_ts=1_000.0)
    assert summary["events_scanned"] == 0
    assert summary["detections"] == 0
    assert summary["detection_gaps"] == ["Undetected RCE"]


# ── write-once MTTD ─────────────────────────────────────────────────────────


def _kerberoast_hit(detection_ts: float) -> DetectionEvent:
    rule = DetectionRule(
        id="DCEP-T1558.003-kerberoast",
        title="Kerberoast",
        level="high",
        mitre=("T1558.003",),
    )
    return DetectionEvent(rule=rule, matched_fields={}, event_ts=100.0, detection_ts=detection_ts)


_DETECT_KEY = "detection::DCEP-T1558.003-kerberoast::deadbeefdeadbeef::0"


def test_rescan_preserves_first_seen_mttd(tmp_path: Path) -> None:
    graph = KnowledgeGraph()
    _record_hit(graph, "sandbox.tmux.main", _kerberoast_hit(detection_ts=105.0), key=_DETECT_KEY)
    first = graph.by_kind(NodeKind.DETECTION_FIRED)[0]
    assert first.props["mttd_seconds"] == 5.0

    # Same logged event (same content key) re-detected far later — must not inflate.
    _record_hit(graph, "sandbox.tmux.main", _kerberoast_hit(detection_ts=900.0), key=_DETECT_KEY)
    fired = graph.by_kind(NodeKind.DETECTION_FIRED)
    assert len(fired) == 1  # idempotent: same content key
    assert fired[0].props["mttd_seconds"] == 5.0
    assert fired[0].props["detection_ts"] == 105.0


def test_rescan_of_untimestamped_log_is_idempotent(tmp_path: Path) -> None:
    """The default case: session logs have no leading timestamp, so the tap
    stamps each line with scan wall-clock. Re-scanning at a *different* wall
    clock must NOT create new DetectionFired nodes or inflate detections —
    the regression the old event_ts-based key caused."""
    graph = KnowledgeGraph()
    first = _scan(graph, tmp_path, _KERBEROAST, _DCSYNC, now_ts=1_000.0)
    assert first["detections"] == 2
    n_after_first = len(graph.by_kind(NodeKind.DETECTION_FIRED))
    assert n_after_first == 2

    # Re-scan the identical logs much later (fresh synthetic event_ts).
    second = _scan(graph, tmp_path, _KERBEROAST, _DCSYNC, now_ts=9_999.0)
    assert second["detections"] == 2
    assert len(graph.by_kind(NodeKind.DETECTION_FIRED)) == 2  # not 4


def test_distinct_lines_firing_same_rule_get_distinct_nodes(tmp_path: Path) -> None:
    """Two different commands that trip the same rule must be two nodes — the
    old key collapsed them whenever they shared a (synthetic) event_ts."""
    graph = KnowledgeGraph()
    other_kerberoast = "$ GetUserSPNs.py -request -dc-ip 10.0.0.2 other.local/svc2"
    summary = _scan(graph, tmp_path, _KERBEROAST, other_kerberoast, now_ts=1_000.0)
    fired = graph.by_kind(NodeKind.DETECTION_FIRED)
    assert summary["detections"] == 2
    assert len(fired) == 2
    assert len({n.props["key"] for n in fired}) == 2


# ── tool wrapper (transaction + workspace resolution) ───────────────────────


class _FakeStore:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def load_graph(self) -> KnowledgeGraph:
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes) -> int:
        for n in nodes:
            self.graph.upsert_node(n)
        return len(list(nodes))

    def batch_upsert_edges(self, edges) -> int:
        for e in edges:
            self.graph.upsert_edge(e)
        return len(list(edges))


def test_blue_cell_scan_tool_persists_through_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    workspace = _workspace_with(tmp_path, _DCSYNC)

    result = json.loads(blue_cell_scan.invoke({"workspace_path": workspace}))

    assert result["detections"] == 1
    assert result["techniques_detected"] == ["T1003.006"]
    assert len(fake.graph.by_kind(NodeKind.DETECTION_FIRED)) == 1
