"""Tests for AgentStateMiddleware — state schema + reminder injection."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from decepticon.middleware.agentstate import (
    AgentStateExtension,
    AgentStateMiddleware,
)


def test_state_schema_extends_agent_state():
    """The middleware exposes a state schema with the three scratch keys."""
    annotations = AgentStateExtension.__annotations__
    assert "agent_todo" in annotations
    assert "agent_notes" in annotations
    assert "agent_thinking" in annotations


def test_before_model_with_empty_state_is_noop():
    """No reminder is injected when the agent has no scratch yet."""
    mw = AgentStateMiddleware()
    state = {"messages": [HumanMessage("hi")]}
    out = mw.before_model(state, runtime=None)
    assert out is None


def test_before_model_renders_open_todos():
    """Open todos appear in the injected SystemMessage."""
    mw = AgentStateMiddleware()
    state = {
        "messages": [HumanMessage("hi")],
        "agent_todo": [
            {"id": 1, "item": "scan port 80", "status": "open", "ts": "t0"},
            {"id": 2, "item": "exploit RCE", "status": "done", "ts": "t1"},
        ],
    }
    out = mw.before_model(state, runtime=None)
    assert out is not None
    msgs = out["messages"]
    sys = next(m for m in msgs if isinstance(m, SystemMessage))
    assert "1 open todo" in sys.content
    assert "scan port 80" in sys.content
    assert "exploit RCE" not in sys.content  # done todos hidden in reminder


def test_before_model_summarises_notes_and_thoughts():
    mw = AgentStateMiddleware()
    state = {
        "messages": [],
        "agent_notes": [{"ts": "t0", "note": "x"}, {"ts": "t1", "note": "y"}],
        "agent_thinking": [{"ts": "t2", "thought": "z"}],
    }
    out = mw.before_model(state, runtime=None)
    assert out is not None
    body = next(m.content for m in out["messages"] if isinstance(m, SystemMessage))
    assert "2 note(s)" in body
    assert "1 thought" in body


def test_before_model_truncates_long_todo_list():
    mw = AgentStateMiddleware()
    todos = [{"id": i, "item": f"task-{i}", "status": "open", "ts": "t"} for i in range(1, 12)]
    state = {"messages": [], "agent_todo": todos}
    out = mw.before_model(state, runtime=None)
    assert out is not None
    body = next(m.content for m in out["messages"] if isinstance(m, SystemMessage))
    assert "task-1" in body
    assert "+3 more" in body  # 11 open, first 8 listed, 3 trailing


def test_inject_reminder_disabled_skips_systemmessage():
    """``inject_reminder=False`` keeps the schema but stops the side-effect."""
    mw = AgentStateMiddleware(inject_reminder=False)
    state = {
        "messages": [],
        "agent_todo": [{"id": 1, "item": "x", "status": "open", "ts": "t0"}],
    }
    assert mw.before_model(state, runtime=None) is None


def test_state_schema_assigned_to_middleware_class():
    """LangGraph reads ``state_schema`` to merge schemas — the attribute must exist."""
    assert AgentStateMiddleware.state_schema is AgentStateExtension
