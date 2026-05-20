"""Tests for MentorMiddleware loop detection.

These tests are framework-agnostic — they construct minimal LangChain
AIMessage objects and verify the middleware's signature collector +
loop detector behave correctly. No LangGraph or Decepticon-orchestrator
integration required.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from decepticon.middleware.mentor import MentorMiddleware, _CallSignature


def _ai_msg(tool: str, args: dict) -> AIMessage:
    """Construct an AIMessage with one tool_call entry."""
    return AIMessage(
        content="",
        tool_calls=[{"name": tool, "args": args, "id": f"call_{tool}"}],
    )


class TestCallSignature:
    def test_same_args_same_signature(self) -> None:
        s1 = _CallSignature.from_tool_call({"name": "bash", "args": {"cmd": "ls /tmp"}})
        s2 = _CallSignature.from_tool_call({"name": "bash", "args": {"cmd": "ls /tmp"}})
        assert s1 == s2

    def test_different_args_different_signature(self) -> None:
        s1 = _CallSignature.from_tool_call({"name": "bash", "args": {"cmd": "ls /tmp"}})
        s2 = _CallSignature.from_tool_call({"name": "bash", "args": {"cmd": "ls /var"}})
        assert s1 != s2

    def test_different_tool_different_signature(self) -> None:
        s1 = _CallSignature.from_tool_call({"name": "bash", "args": {"cmd": "ls"}})
        s2 = _CallSignature.from_tool_call({"name": "read", "args": {"cmd": "ls"}})
        assert s1 != s2

    def test_arg_order_independent(self) -> None:
        s1 = _CallSignature.from_tool_call(
            {"name": "fetch", "args": {"url": "http://x", "headers": {"a": 1}}}
        )
        s2 = _CallSignature.from_tool_call(
            {"name": "fetch", "args": {"headers": {"a": 1}, "url": "http://x"}}
        )
        assert s1 == s2


class TestMentorMiddleware:
    def test_no_messages_no_warn(self) -> None:
        m = MentorMiddleware(min_repeat_count=3)
        result = m.before_model({"messages": []}, runtime=None)
        assert result is None

    def test_below_threshold_no_warn(self) -> None:
        m = MentorMiddleware(min_repeat_count=5)
        msgs = [_ai_msg("bash", {"cmd": "id"}) for _ in range(3)]
        result = m.before_model({"messages": msgs}, runtime=None)
        assert result is None

    def test_at_threshold_warns(self) -> None:
        m = MentorMiddleware(min_repeat_count=5)
        msgs = [_ai_msg("bash", {"cmd": "id"}) for _ in range(5)]
        result = m.before_model({"messages": msgs}, runtime=None)
        assert result is not None
        text = result["messages"][0].content
        assert "MENTOR" in text
        assert "5×" in text
        assert "`bash`" in text

    def test_cooldown_suppresses_repeat_warn(self) -> None:
        m = MentorMiddleware(min_repeat_count=3, cooldown_turns=3)
        msgs = [_ai_msg("scan", {"target": "10.0.0.1"}) for _ in range(3)]
        # Turn 1 — should warn
        r1 = m.before_model({"messages": msgs}, runtime=None)
        assert r1 is not None
        # Turn 2 — same loop still active, but cooldown should suppress
        r2 = m.before_model({"messages": msgs}, runtime=None)
        assert r2 is None
        r3 = m.before_model({"messages": msgs}, runtime=None)
        assert r3 is None
        # After cooldown_turns turns elapse, re-warn
        r4 = m.before_model({"messages": msgs}, runtime=None)
        assert r4 is not None

    def test_mixed_signatures_dominant_wins(self) -> None:
        m = MentorMiddleware(min_repeat_count=4)
        msgs = (
            [_ai_msg("bash", {"cmd": "ls"})] * 5
            + [_ai_msg("read", {"path": "/tmp/x"})] * 2
        )
        result = m.before_model({"messages": msgs}, runtime=None)
        assert result is not None
        text = result["messages"][0].content
        assert "`bash`" in text  # dominant
        assert "5×" in text

    def test_non_ai_messages_ignored(self) -> None:
        m = MentorMiddleware(min_repeat_count=3)
        msgs = [HumanMessage(content="hello") for _ in range(5)] + [
            _ai_msg("bash", {"cmd": "ls"})
        ]
        result = m.before_model({"messages": msgs}, runtime=None)
        # Only 1 AI message → below threshold
        assert result is None

    def test_string_args_handled(self) -> None:
        """args sometimes arrive as JSON strings rather than dicts."""
        m = MentorMiddleware(min_repeat_count=3)
        msgs = []
        for _ in range(3):
            msgs.append(
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "bash", "args": '{"cmd": "ls"}', "id": "x"}
                    ],
                )
            )
        result = m.before_model({"messages": msgs}, runtime=None)
        assert result is not None


@pytest.mark.parametrize("threshold", [3, 5, 8])
def test_threshold_respected(threshold: int) -> None:
    m = MentorMiddleware(min_repeat_count=threshold)
    just_below = [_ai_msg("x", {"y": 1}) for _ in range(threshold - 1)]
    at = [_ai_msg("x", {"y": 1}) for _ in range(threshold)]
    assert m.before_model({"messages": just_below}, runtime=None) is None
    m2 = MentorMiddleware(min_repeat_count=threshold)
    assert m2.before_model({"messages": at}, runtime=None) is not None
