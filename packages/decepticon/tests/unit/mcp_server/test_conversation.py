"""Tests for decepticon.mcp_server.conversation (ThreadState parsing)."""

from __future__ import annotations

from typing import Any

from decepticon.mcp_server.conversation import build_engagement_state, build_transcript

_STATE: dict[str, Any] = {
    "values": {
        "engagement_name": "eng-1",
        "scan_scope": {"targets": ["https://x"]},
        "messages": [
            {"type": "human", "content": "Test the login API."},
            {
                "type": "ai",
                "content": "On it — delegating recon.",
                "tool_calls": [{"name": "task", "args": {"subagent_type": "recon"}}],
            },
            {"type": "tool", "name": "task", "content": "Found 3 open ports."},
        ],
    }
}


def test_transcript_parses_roles_and_delegations() -> None:
    t = build_transcript(_STATE, thread_id="t", run_status="running", after_index=0, limit=40)
    assert t.total == 3
    assert t.next_index == 3
    assert [m.role for m in t.messages] == ["user", "assistant", "tool"]
    assert t.messages[1].tool_calls == ["task(recon)"]
    assert t.messages[2].name == "task"
    assert t.messages[0].text == "Test the login API."


def test_transcript_windowing() -> None:
    t = build_transcript(_STATE, thread_id="t", run_status="none", after_index=1, limit=1)
    assert len(t.messages) == 1
    assert t.messages[0].index == 1
    assert t.next_index == 2


def test_transcript_flattens_content_blocks() -> None:
    state = {
        "values": {
            "messages": [
                {
                    "type": "ai",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "tool_use", "name": "x"},
                    ],
                }
            ]
        }
    }
    t = build_transcript(state, thread_id="t", run_status="running", after_index=0, limit=40)
    assert t.messages[0].text == "hello"


def test_transcript_handles_empty_state() -> None:
    t = build_transcript({}, thread_id="t", run_status="none", after_index=0, limit=40)
    assert t.total == 0
    assert t.messages == []


def test_engagement_state_excludes_messages() -> None:
    s = build_engagement_state(_STATE, thread_id="t", run_status="running")
    assert s.engagement_name == "eng-1"
    assert s.message_count == 3
    assert "messages" not in s.values
    assert s.values["scan_scope"] == {"targets": ["https://x"]}


def test_engagement_state_compacts_large_values() -> None:
    state = {"values": {"blob": "x" * 5000, "messages": []}}
    s = build_engagement_state(state, thread_id="t", run_status="none")
    assert "omitted" in str(s.values["blob"])
