"""Unit tests for the per-agent state tools.

These tests exercise the tools as plain Python callables (the
``Command`` returned object lets us assert on both the state delta and the
emitted ToolMessage) without needing a full LangGraph runtime.
"""

from __future__ import annotations

import pytest
from langgraph.types import Command

from decepticon.tools.agentstate import AGENT_STATE_TOOLS
from decepticon.tools.agentstate.tools import (
    AGENT_STATE_TOOL_NAMES,
    agent_finish,
    agent_note_add,
    agent_note_list,
    agent_thinking,
    agent_todo_add,
    agent_todo_complete,
    agent_todo_list,
)


def _invoke(tool, *, state: dict | None = None, **kwargs) -> Command:
    """Invoke a langchain @tool-decorated callable like the runtime would.

    Tools that declare ``InjectedToolCallId`` reject plain kwarg payloads —
    LangChain requires the full ToolCall envelope, mirroring how the agent
    runtime invokes them.
    """
    args = dict(kwargs)
    if state is not None:
        args["state"] = state
    payload = {
        "name": getattr(tool, "name", "tool"),
        "type": "tool_call",
        "id": "tc-1",
        "args": args,
    }
    return tool.invoke(payload)


def _upd(cmd: Command) -> dict:
    """Return ``cmd.update`` narrowed to a dict (it is Optional on Command)."""
    return getattr(cmd, "update", None) or {}


def _msg_text(cmd: Command) -> str:
    msgs = _upd(cmd)["messages"]
    assert msgs, "tool emitted no messages"
    return msgs[0].content


# ── registry surface ────────────────────────────────────────────────


def test_registry_lists_all_tools():
    """All seven scratch tools are exported from the package."""
    names = {t.name for t in AGENT_STATE_TOOLS}
    assert names == AGENT_STATE_TOOL_NAMES


# ── thinking ────────────────────────────────────────────────────────


def test_agent_thinking_appends_entry():
    state: dict = {}
    cmd = _invoke(agent_thinking, thought="recon first", state=state)
    log = _upd(cmd)["agent_thinking"]
    assert len(log) == 1
    assert log[0]["thought"] == "recon first"
    assert "ts" in log[0]
    assert "thinking #1 recorded" in _msg_text(cmd)


def test_agent_thinking_rejects_blank():
    cmd = _invoke(agent_thinking, thought="   ", state={})
    assert "agent_thinking" not in _upd(cmd)
    assert "rejected" in _msg_text(cmd)


def test_agent_thinking_preserves_history():
    state = {"agent_thinking": [{"ts": "t0", "thought": "old"}]}
    cmd = _invoke(agent_thinking, thought="new", state=state)
    log = _upd(cmd)["agent_thinking"]
    assert len(log) == 2
    assert log[0]["thought"] == "old"
    assert log[1]["thought"] == "new"


# ── todo ────────────────────────────────────────────────────────────


def test_agent_todo_add_creates_entry_with_id_1():
    state: dict = {}
    cmd = _invoke(agent_todo_add, item="enumerate users", state=state)
    todos = _upd(cmd)["agent_todo"]
    assert len(todos) == 1
    assert todos[0] == {
        "id": 1,
        "item": "enumerate users",
        "status": "open",
        "ts": todos[0]["ts"],
    }


def test_agent_todo_add_rejects_blank():
    cmd = _invoke(agent_todo_add, item="", state={})
    assert "agent_todo" not in _upd(cmd)
    assert "rejected" in _msg_text(cmd)


def test_agent_todo_add_increments_id_monotonically():
    state = {"agent_todo": [{"id": 5, "item": "old", "status": "open", "ts": "t0"}]}
    cmd = _invoke(agent_todo_add, item="new", state=state)
    todos = _upd(cmd)["agent_todo"]
    assert todos[-1]["id"] == 6


def test_agent_todo_complete_marks_done():
    state = {"agent_todo": [{"id": 1, "item": "x", "status": "open", "ts": "t0"}]}
    cmd = _invoke(agent_todo_complete, todo_id=1, state=state)
    todos = _upd(cmd)["agent_todo"]
    assert todos[0]["status"] == "done"
    assert "completed_ts" in todos[0]
    assert "completed" in _msg_text(cmd)


def test_agent_todo_complete_unknown_id_is_noop():
    state = {"agent_todo": [{"id": 1, "item": "x", "status": "open", "ts": "t0"}]}
    cmd = _invoke(agent_todo_complete, todo_id=99, state=state)
    assert "agent_todo" not in _upd(cmd)
    assert "not found" in _msg_text(cmd)


def test_agent_todo_list_renders_checkbox_format():
    state = {
        "agent_todo": [
            {"id": 1, "item": "alpha", "status": "open", "ts": "t0"},
            {"id": 2, "item": "beta", "status": "done", "ts": "t1"},
        ]
    }
    cmd = _invoke(agent_todo_list, state=state)
    body = _msg_text(cmd)
    assert "[ ] #1 — alpha" in body
    assert "[x] #2 — beta" in body


def test_agent_todo_list_empty_returns_placeholder():
    cmd = _invoke(agent_todo_list, state={})
    assert "(no todos)" in _msg_text(cmd)


# ── notes ───────────────────────────────────────────────────────────


def test_agent_note_add_appends():
    state: dict = {}
    cmd = _invoke(agent_note_add, note="found admin panel at /admin", state=state)
    notes = _upd(cmd)["agent_notes"]
    assert len(notes) == 1
    assert notes[0]["note"] == "found admin panel at /admin"


def test_agent_note_add_rejects_blank():
    cmd = _invoke(agent_note_add, note="", state={})
    assert "agent_notes" not in _upd(cmd)


def test_agent_note_list_renders_all_notes():
    state = {
        "agent_notes": [
            {"ts": "t0", "note": "first"},
            {"ts": "t1", "note": "second"},
        ]
    }
    cmd = _invoke(agent_note_list, state=state)
    body = _msg_text(cmd)
    assert "#1" in body and "first" in body
    assert "#2" in body and "second" in body


def test_agent_note_list_empty_returns_placeholder():
    cmd = _invoke(agent_note_list, state={})
    assert "(no notes)" in _msg_text(cmd)


# ── finish ──────────────────────────────────────────────────────────


def test_agent_finish_clears_state_and_summarises():
    state = {
        "agent_todo": [
            {"id": 1, "item": "open task", "status": "open", "ts": "t0"},
            {"id": 2, "item": "done task", "status": "done", "ts": "t1"},
        ],
        "agent_notes": [{"ts": "t2", "note": "found XSS"}],
        "agent_thinking": [{"ts": "t3", "thought": "tried payload A"}],
    }
    cmd = _invoke(agent_finish, summary="objective complete", state=state)
    assert _upd(cmd)["agent_todo"] == []
    assert _upd(cmd)["agent_notes"] == []
    assert _upd(cmd)["agent_thinking"] == []
    body = _msg_text(cmd)
    assert "objective complete" in body
    assert "found XSS" in body
    assert "tried payload A" in body
    assert "open task" in body
    assert "done task" in body
    # summary header includes counts so the orchestrator can scan quickly
    assert "todos (2 total, 1 open)" in body


def test_agent_finish_without_state_still_works():
    cmd = _invoke(agent_finish, summary="trivial", state={})
    body = _msg_text(cmd)
    assert "trivial" in body
    # no scratch sections rendered when state is empty
    assert "todos" not in body
    assert "notes" not in body


def test_agent_finish_blank_summary_uses_placeholder():
    cmd = _invoke(agent_finish, summary="   ", state={})
    body = _msg_text(cmd)
    assert "(no summary)" in body


# ── coercion robustness ────────────────────────────────────────────


@pytest.mark.parametrize(
    "junk",
    [None, "string-not-list", 42, {"id": 1}, [1, 2, "three"]],
    ids=["none", "string", "int", "dict", "mixed-list"],
)
def test_tools_coerce_garbage_state_values(junk):
    """A poisoned state value (wrong type) must not crash any tool."""
    state = {"agent_todo": junk, "agent_notes": junk, "agent_thinking": junk}
    # Each read tool returns a Command without raising
    assert _invoke(agent_todo_list, state=state)
    assert _invoke(agent_note_list, state=state)
    # Mutators reset to a valid list before append
    cmd = _invoke(agent_todo_add, item="x", state=state)
    assert isinstance(_upd(cmd)["agent_todo"], list)
    assert _upd(cmd)["agent_todo"][0]["id"] == 1
