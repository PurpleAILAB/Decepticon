"""Tests for DetectionFeedbackMiddleware — the Red-vs-Blue learning loop.

Verifies the behaviour the adaptive feedback loop depends on: a fast
DetectionFired triggers a stealth reminder, slow detections don't, each
detection surfaces once, and the in-progress objective's OPSEC is escalated
(never loosened). No Neo4j — the graph store is faked.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from decepticon.middleware.detection_feedback import DetectionFeedbackMiddleware
from decepticon.tools.research import _state as state
from decepticon_core.types.kg import KnowledgeGraph, Node, NodeKind


class _FakeStore:
    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph

    def load_graph(self) -> KnowledgeGraph:
        return self._graph.model_copy(deep=True)


def _store_with(monkeypatch: pytest.MonkeyPatch, *fired: Node) -> None:
    graph = KnowledgeGraph()
    for node in fired:
        graph.upsert_node(node)
    monkeypatch.setattr(state, "_store", _FakeStore(graph))


def _run(mw: DetectionFeedbackMiddleware, state_in: dict[str, Any]) -> dict | None:
    """Drive the real before_model hook (cast around its AgentState signature)."""
    return mw.before_model(cast("Any", state_in), cast("Any", None))


def _detection(key: str, mttd: float, *, technique: str = "T1558.003") -> Node:
    return Node.make(
        NodeKind.DETECTION_FIRED,
        "Kerberoast",
        key=key,
        rule_id=f"DCEP-{technique}-rule",
        rule_title="Kerberoast",
        mitre=[technique],
        mttd_seconds=mttd,
    )


def _objective(oid: str, status: str, opsec: str) -> dict[str, Any]:
    return {"id": oid, "status": status, "opsec": opsec}


def test_fast_detection_injects_stealth_reminder(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    update = _run(DetectionFeedbackMiddleware(), {})
    assert update is not None
    content = update["messages"][0].content
    assert "DCEP-T1558.003-rule" in content
    assert "T1558.003" in content
    assert "OPSEC" in content or "opsec" in content
    assert "objectives" not in update  # no OPPLAN state present


def test_reminder_does_not_claim_escalation_when_no_objectives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    update = _run(DetectionFeedbackMiddleware(), {})
    assert update is not None
    content = update["messages"][0].content
    assert "has already been escalated" not in content


def test_reminder_claims_escalation_only_when_objective_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    update = _run(
        DetectionFeedbackMiddleware(),
        {"objectives": [_objective("OBJ-1", "in-progress", "loud")]},
    )
    assert update is not None
    assert "has already been escalated" in update["messages"][0].content


def test_reminder_does_not_claim_escalation_when_already_stricter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    update = _run(
        DetectionFeedbackMiddleware(),
        {"objectives": [_objective("OBJ-1", "in-progress", "silent")]},
    )
    assert update is not None
    assert "has already been escalated" not in update["messages"][0].content


def test_slow_detection_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch, _detection("d::1", 30.0))
    assert _run(DetectionFeedbackMiddleware(), {}) is None


def test_threshold_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch, _detection("d::1", 3.0))
    assert _run(DetectionFeedbackMiddleware(mttd_threshold=2.0), {}) is None
    assert _run(DetectionFeedbackMiddleware(mttd_threshold=5.0), {}) is not None


def test_each_detection_surfaces_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    mw = DetectionFeedbackMiddleware()
    assert _run(mw, {}) is not None
    assert _run(mw, {}) is None  # already surfaced


def test_escalates_in_progress_objective_opsec(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    state_in = {
        "objectives": [
            _objective("OBJ-1", "in-progress", "loud"),
            _objective("OBJ-2", "pending", "loud"),
        ]
    }
    update = _run(DetectionFeedbackMiddleware(), state_in)
    assert update is not None
    by_id = {o["id"]: o for o in update["objectives"]}
    assert by_id["OBJ-1"]["opsec"] == "careful"  # escalated
    assert by_id["OBJ-2"]["opsec"] == "loud"  # pending → untouched


def test_does_not_loosen_a_stricter_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch, _detection("d::1", 1.2))
    state_in = {"objectives": [_objective("OBJ-1", "in-progress", "silent")]}
    update = _run(DetectionFeedbackMiddleware(), state_in)
    assert update is not None
    # silent is stricter than the careful target → no objective rewrite.
    assert "objectives" not in update


def test_no_detections_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(monkeypatch)
    assert _run(DetectionFeedbackMiddleware(), {}) is None
