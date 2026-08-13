"""Unit tests for the pure-logic helpers in ``decepticon.tools.opplan``.

Covers the three silent-corruption-prone paths that previously had **zero**
direct coverage:

* the OPPLAN status-transition state machine (``_is_valid_transition`` /
  ``_valid_next`` / ``_VALID_TRANSITIONS``) — an over-permissive table lets
  an agent skip the kill-chain ordering;
* the persisted JSON payload builder (``_build_opplan_payload``) — a
  miscounted summary or unstable ordering corrupts the on-disk plan;
* the agent-facing markdown formatter (``_format_opplan_for_agent``),
  whose ``parent_id`` task-tree renderer carries a cycle guard that
  defends against a malformed / prompt-injected plan driving the agent
  into unbounded recursion.

No network / docker / LLM dependencies.
"""

from __future__ import annotations

import pytest

from decepticon.tools.opplan import (
    _BLOCKED_MIN_NOTES_CHARS,
    _VALID_TRANSITIONS,
    OPPLAN_FILE_SCHEMA_VERSION,
    _blocked_gate_enabled,
    _blocked_gate_error,
    _build_opplan_payload,
    _format_opplan_for_agent,
    _is_valid_transition,
    _valid_next,
)
from decepticon_core.types.engagement import (
    OPPLAN,
    Objective,
    ObjectivePhase,
    ObjectiveStatus,
)

# ---------------------------------------------------------------- helpers


def _obj(
    oid: str,
    *,
    status: ObjectiveStatus = ObjectiveStatus.PENDING,
    priority: int = 1,
    phase: ObjectivePhase = ObjectivePhase.RECON,
    title: str = "t",
    parent_id: str | None = None,
) -> Objective:
    return Objective(
        id=oid,
        phase=phase,
        title=title,
        description="d",
        acceptance_criteria=["c"],
        priority=priority,
        status=status,
        parent_id=parent_id,
    )


def _row(oid: str, **kw: object) -> dict:
    """A formatter row dict (``_format_opplan_for_agent`` consumes dicts)."""
    base: dict = {
        "id": oid,
        "phase": "recon",
        "title": oid,
        "status": "pending",
        "priority": 1,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------- transitions


def test_pending_can_only_start_or_cancel():
    assert _is_valid_transition("pending", "in-progress") is True
    assert _is_valid_transition("pending", "cancelled") is True
    # cannot jump straight to a terminal/blocked state from pending
    assert _is_valid_transition("pending", "completed") is False
    assert _is_valid_transition("pending", "blocked") is False


def test_in_progress_can_complete_block_or_cancel():
    for nxt in ("completed", "blocked", "cancelled"):
        assert _is_valid_transition("in-progress", nxt) is True
    assert _is_valid_transition("in-progress", "pending") is False


def test_blocked_can_retry_complete_or_cancel():
    for nxt in ("in-progress", "completed", "cancelled"):
        assert _is_valid_transition("blocked", nxt) is True
    assert _is_valid_transition("blocked", "pending") is False


def test_terminal_states_allow_no_transition():
    for terminal in ("completed", "cancelled"):
        for nxt in ("pending", "in-progress", "completed", "blocked", "cancelled"):
            assert _is_valid_transition(terminal, nxt) is False
        assert _valid_next(terminal) == ""


def test_unknown_source_state_is_never_valid():
    assert _is_valid_transition("bogus", "in-progress") is False
    assert _valid_next("bogus") == ""


def test_no_state_transitions_to_itself():
    for state in _VALID_TRANSITIONS:
        assert _is_valid_transition(state, state) is False


def test_valid_next_is_sorted_and_comma_joined():
    assert _valid_next("in-progress") == "blocked, cancelled, completed"
    assert _valid_next("pending") == "cancelled, in-progress"


def test_transition_table_only_references_known_statuses():
    known = {s.value for s in ObjectiveStatus}
    for src, targets in _VALID_TRANSITIONS.items():
        assert src in known
        for target in targets:
            assert target in known


# ---------------------------------------------------------------- payload


def test_payload_summary_counts_each_status():
    plan = OPPLAN(
        engagement_name="eng",
        threat_profile="apt",
        objectives=[
            _obj("OBJ-002", status=ObjectiveStatus.COMPLETED, priority=2),
            _obj("OBJ-001", status=ObjectiveStatus.IN_PROGRESS, priority=1),
            _obj("OBJ-003", status=ObjectiveStatus.BLOCKED, priority=3),
            _obj("OBJ-004", status=ObjectiveStatus.PENDING, priority=4),
        ],
    )
    payload = _build_opplan_payload(plan)
    assert payload["schema_version"] == OPPLAN_FILE_SCHEMA_VERSION
    assert payload["engagement_name"] == "eng"
    assert payload["threat_profile"] == "apt"
    assert payload["summary"] == {
        "total": 4,
        "pending": 1,
        "in_progress": 1,
        "completed": 1,
        "blocked": 1,
        "cancelled": 0,
    }


def test_payload_sorts_objectives_by_id_for_stable_diffs():
    plan = OPPLAN(
        engagement_name="e",
        threat_profile="t",
        objectives=[_obj("OBJ-003"), _obj("OBJ-001"), _obj("OBJ-002")],
    )
    payload = _build_opplan_payload(plan)
    assert [o["id"] for o in payload["objectives"]] == ["OBJ-001", "OBJ-002", "OBJ-003"]


def test_payload_empty_plan_has_zeroed_summary():
    plan = OPPLAN(engagement_name="e", threat_profile="t", objectives=[])
    payload = _build_opplan_payload(plan)
    assert payload["objectives"] == []
    assert payload["summary"]["total"] == 0
    assert all(
        payload["summary"][k] == 0
        for k in ("pending", "in_progress", "completed", "blocked", "cancelled")
    )


def test_payload_round_trips_back_into_opplan_model():
    plan = OPPLAN(
        engagement_name="e",
        threat_profile="t",
        objectives=[_obj("OBJ-001", status=ObjectiveStatus.IN_PROGRESS)],
    )
    payload = _build_opplan_payload(plan)
    # The wrapper fields (schema_version / saved_at / summary) are a superset
    # of the runtime model and must be dropped silently when reloaded.
    restored = OPPLAN(**payload)
    assert restored.engagement_name == "e"
    assert len(restored.objectives) == 1
    assert restored.objectives[0].id == "OBJ-001"
    assert restored.objectives[0].status == ObjectiveStatus.IN_PROGRESS


# ---------------------------------------------------------------- formatter


def test_format_header_and_progress_line():
    out = _format_opplan_for_agent(
        [_row("OBJ-001", status="completed"), _row("OBJ-002", status="blocked")],
        "my-eng",
        "apt29",
    )
    assert "# OPPLAN: my-eng" in out
    assert "Threat Profile: apt29" in out
    assert "Progress: 1/2 completed, 1 blocked" in out


def test_format_table_is_sorted_by_priority():
    out = _format_opplan_for_agent(
        [_row("OBJ-A", priority=3), _row("OBJ-B", priority=1), _row("OBJ-C", priority=2)],
        "e",
        "t",
    )
    ids = [line.split("|")[1].strip() for line in out.splitlines() if line.startswith("| OBJ-")]
    assert ids == ["OBJ-B", "OBJ-C", "OBJ-A"]


def test_format_blocked_by_joined_and_owner_fallback():
    out = _format_opplan_for_agent(
        [_row("OBJ-1", blocked_by=["OBJ-9", "OBJ-8"], owner="")],
        "e",
        "t",
    )
    row = next(line for line in out.splitlines() if line.startswith("| OBJ-1 "))
    assert "OBJ-9, OBJ-8" in row
    assert "| - |" in row  # empty owner renders as a dash


def test_format_has_no_task_tree_when_flat():
    out = _format_opplan_for_agent([_row("OBJ-1"), _row("OBJ-2")], "e", "t")
    assert "## Task Tree" not in out


def test_format_renders_task_tree_when_hierarchical():
    out = _format_opplan_for_agent(
        [_row("ROOT"), _row("CHILD", parent_id="ROOT")],
        "e",
        "t",
    )
    assert "## Task Tree" in out
    tree = out.split("## Task Tree", 1)[1]
    assert "ROOT" in tree
    assert "CHILD" in tree


def test_format_tree_status_markers():
    out = _format_opplan_for_agent(
        [
            _row("R"),
            _row("C1", parent_id="R", status="completed"),
            _row("C2", parent_id="R", status="blocked"),
            _row("C3", parent_id="R", status="in-progress"),
            _row("C4", parent_id="R", status="cancelled"),
            _row("C5", parent_id="R", status="pending"),
        ],
        "e",
        "t",
    )
    tree = out.split("## Task Tree", 1)[1]
    assert "[x] C1" in tree
    assert "[!] C2" in tree
    assert "[~] C3" in tree
    assert "[-] C4" in tree
    assert "[ ] C5" in tree


def test_format_tree_cycle_guard_terminates_on_duplicate_id():
    # A duplicate id ("A") nested under its own descendant would re-enter
    # _render("A", ...) forever without the visited guard. The guard must
    # render each reachable node exactly once and terminate.
    rows = [
        _row("A"),  # root (no parent_id)
        _row("B", parent_id="A"),
        _row("A", parent_id="B"),  # cycle bait: same id deeper in the tree
    ]
    out = _format_opplan_for_agent(rows, "e", "t")
    tree = out.split("## Task Tree", 1)[1]
    tree_nodes = [line for line in tree.splitlines() if line.strip().startswith("- [")]
    # root A + child B; the re-entrant duplicate "A" under B is skipped.
    assert len(tree_nodes) == 2


def test_format_next_picks_lowest_priority_actionable():
    out = _format_opplan_for_agent(
        [
            _row("OBJ-3", status="pending", priority=3),
            _row("OBJ-1", status="completed", priority=1),  # done -> not actionable
            _row("OBJ-2", status="in-progress", priority=2),
        ],
        "e",
        "t",
    )
    assert "Next: OBJ-2 \u2014" in out  # em-dash separator


def test_format_all_complete_message():
    out = _format_opplan_for_agent(
        [_row("OBJ-1", status="completed"), _row("OBJ-2", status="completed")],
        "e",
        "t",
    )
    assert "ALL OBJECTIVES COMPLETE" in out


def test_format_no_actionable_when_only_blocked():
    out = _format_opplan_for_agent([_row("OBJ-1", status="blocked")], "e", "t")
    assert "No actionable objectives" in out


def test_format_empty_plan_is_safe():
    out = _format_opplan_for_agent([], "eng", "threat")
    assert "Progress: 0/0 completed" in out
    assert "No actionable objectives" in out


# ---------------------------------------------------------------- blocked gate


class TestBlockedGate:
    """``_blocked_gate_error`` — the evidence bar for ``status="blocked"``.

    A block verdict parks an attack lane; a false one once hid an
    engagement's top finding for ~14 days. The gate forces blocked notes to
    carry substance (length) and an evidence reference (artifact / matrix /
    liveness / operator adjudication).
    """

    @pytest.fixture(autouse=True)
    def _gate_on(self, monkeypatch):
        monkeypatch.delenv("DECEPTICON_OPPLAN_BLOCKED_GATE", raising=False)

    def test_empty_notes_rejected(self):
        err = _blocked_gate_error("")
        assert err is not None
        assert "Cannot mark blocked" in err

    def test_short_notes_rejected(self):
        err = _blocked_gate_error("WAF blocks everything. Giving up.")
        assert err is not None
        assert "substantiate" in err

    def test_long_notes_without_evidence_marker_rejected(self):
        notes = (
            "Spent the entire dispatch trying every payload variant I could "
            "think of against the login endpoint and none of them produced "
            "anything useful at all, so this lane is done."
        )
        assert len(notes) >= _BLOCKED_MIN_NOTES_CHARS
        err = _blocked_gate_error(notes)
        assert err is not None
        assert "no evidence marker" in err

    @pytest.mark.parametrize(
        "marker",
        [
            "EXIT_REPORT",
            "PIVOT",
            "CONVERGED",
            "RECON_BLOCKED",
            "RECON_BUDGET_EXHAUSTED",
            "SUMMARY.md",
            "differential",
            "unreachable",
            "liveness",
            "operator",
            "scope",
        ],
    )
    def test_each_evidence_marker_accepted(self, marker: str):
        notes = (
            f"All vectors exhausted per the documented {marker} evidence; "
            "every bypass class against every candidate endpoint returned "
            "negative with signatures recorded, and no plausible chain "
            "remains against the current finding set."
        )
        assert _blocked_gate_error(notes) is None

    def test_marker_match_is_case_insensitive(self):
        notes = (
            "Reachability premise disproven by the differential matrix "
            "(default-UA vs browser-UA vs curl_cffi vs browser across public "
            "and api paths) — see exploit/exit_report.md for the capture."
        )
        assert _blocked_gate_error(notes) is None

    def test_gate_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_OPPLAN_BLOCKED_GATE", "0")
        assert _blocked_gate_error("") is None

    @pytest.mark.parametrize("value", ["0", "false", "off", "FALSE"])
    def test_gate_disable_values(self, monkeypatch, value: str):
        monkeypatch.setenv("DECEPTICON_OPPLAN_BLOCKED_GATE", value)
        assert _blocked_gate_enabled() is False

    def test_gate_enabled_by_default_and_other_values(self, monkeypatch):
        monkeypatch.delenv("DECEPTICON_OPPLAN_BLOCKED_GATE", raising=False)
        assert _blocked_gate_enabled() is True
        monkeypatch.setenv("DECEPTICON_OPPLAN_BLOCKED_GATE", "1")
        assert _blocked_gate_enabled() is True
