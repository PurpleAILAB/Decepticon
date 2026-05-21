"""Unit tests for DebateGateMiddleware and the DEBATE_GATE slot factory."""

import json

from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage

from decepticon.agents.middleware_slots import _make_debate_gate
from decepticon.middleware.debate_gate import DebateGateMiddleware


def _request(tool_name: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool_name, "args": {}, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,
    )


def _handler_returning(payload: dict):
    def _handler(request):
        return ToolMessage(content=json.dumps(payload), tool_call_id="call-1")

    return _handler


class TestDebateGateMiddleware:
    def test_blocked_result_gets_guidance_appended(self):
        mw = DebateGateMiddleware()
        result = mw.wrap_tool_call(
            _request("validate_finding"),
            _handler_returning({"validated": True, "promotion": "blocked"}),
        )
        assert "[debate-gate]" in result.content
        assert "debate_finding" in result.content

    def test_promoted_result_passes_through(self):
        mw = DebateGateMiddleware()
        result = mw.wrap_tool_call(
            _request("validate_finding"),
            _handler_returning({"validated": True, "promotion": "promoted"}),
        )
        assert "[debate-gate]" not in result.content

    def test_other_tool_passes_through(self):
        mw = DebateGateMiddleware()
        result = mw.wrap_tool_call(
            _request("kg_query"),
            _handler_returning({"promotion": "blocked"}),
        )
        assert "[debate-gate]" not in result.content

    def test_non_json_content_passes_through(self):
        mw = DebateGateMiddleware()
        result = mw.wrap_tool_call(
            _request("validate_finding"),
            lambda req: ToolMessage(content="plain text output", tool_call_id="call-1"),
        )
        assert result.content == "plain text output"


class TestDebateGateSlotFactory:
    def test_factory_returns_middleware_by_default(self, monkeypatch):
        monkeypatch.delenv("DECEPTICON_DEBATE", raising=False)
        assert isinstance(_make_debate_gate(), DebateGateMiddleware)

    def test_factory_self_skips_when_debate_off(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_DEBATE", "off")
        assert _make_debate_gate() is None
