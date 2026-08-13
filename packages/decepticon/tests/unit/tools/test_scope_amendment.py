"""Unit tests for ``decepticon.tools.interaction.request_scope_amendment``."""

from __future__ import annotations

from unittest.mock import patch

from decepticon.tools.interaction import request_scope_amendment

# Mirrored from the tool module so the tests document the contract.
HEADER_MAX_CHARS = 60


def _invoke(**overrides):
    """Invoke the @tool wrapper with sane defaults; ``overrides`` replace fields.

    Mirrors the ask_user_question test harness: tools that declare
    ``InjectedToolCallId`` require a full ToolCall envelope. Returns the
    unwrapped content so tests assert on the agent-visible payload.
    """
    args: dict = {
        "asset": "przkmatt.com",
        "proposed_action": "passive DNS + HTTP GET only",
        "rationale": "Shares the droplet hosting do.sciforium.com; vhost confusion could leak app data.",
    }
    tool_call_id = overrides.pop("tool_call_id", "tc_1")
    args.update(overrides)
    result = request_scope_amendment.invoke(
        {
            "args": args,
            "name": "request_scope_amendment",
            "type": "tool_call",
            "id": tool_call_id,
        }
    )
    return getattr(result, "content", result)


def test_emits_picker_compatible_payload_with_amendment_context():
    captured: list[dict] = []

    with (
        patch(
            "decepticon.tools.interaction.scope_amendment.get_stream_writer",
            return_value=lambda evt: captured.append(evt),
        ),
        patch(
            "decepticon.tools.interaction.scope_amendment.interrupt",
            return_value="Approve — add to scope",
        ),
    ):
        result = _invoke()

    assert result == "Approve — add to scope"
    assert len(captured) == 1
    event = captured[0]
    # Reuses the ask_user_question contract so existing pickers render it.
    assert event["type"] == "ask_user_question"
    assert event["agent"] == "decepticon"
    assert event["id"] == "tc_1"
    assert event["multi_select"] is False
    assert event["allow_other"] is True
    # Amendment context rides along for clients that render it.
    assert event["asset"] == "przkmatt.com"
    assert event["proposed_action"] == "passive DNS + HTTP GET only"
    assert "vhost confusion" in event["rationale"]
    # The generic-picker question embeds the full context.
    assert "przkmatt.com" in event["question"]
    assert "passive DNS + HTTP GET only" in event["question"]
    assert "vhost confusion" in event["question"]
    labels = [o["label"] for o in event["options"]]
    assert labels == ["Approve — add to scope", "Deny — keep out of scope"]


def test_returns_operator_free_text_constraints_verbatim():
    typed = "Approve, but passive recon only — no active probes"
    with (
        patch(
            "decepticon.tools.interaction.scope_amendment.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.scope_amendment.interrupt",
            return_value=typed,
        ),
    ):
        assert _invoke() == typed


def test_denial_flows_back_verbatim():
    with (
        patch(
            "decepticon.tools.interaction.scope_amendment.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.scope_amendment.interrupt",
            return_value="Deny — keep out of scope",
        ),
    ):
        assert _invoke() == "Deny — keep out of scope"


def test_skips_writer_when_outside_graph_context():
    """get_stream_writer raises outside a graph; the tool must continue."""

    def raising():
        raise RuntimeError("not in a graph context")

    with (
        patch(
            "decepticon.tools.interaction.scope_amendment.get_stream_writer",
            side_effect=raising,
        ),
        patch(
            "decepticon.tools.interaction.scope_amendment.interrupt",
            return_value="Deny — keep out of scope",
        ),
    ):
        assert _invoke() == "Deny — keep out of scope"


def test_truncates_long_header():
    captured: list[dict] = []

    with (
        patch(
            "decepticon.tools.interaction.scope_amendment.get_stream_writer",
            return_value=lambda evt: captured.append(evt),
        ),
        patch(
            "decepticon.tools.interaction.scope_amendment.interrupt",
            return_value="Approve — add to scope",
        ),
    ):
        _invoke(header="X" * (HEADER_MAX_CHARS + 10))

    assert captured[0]["header"] == "X" * HEADER_MAX_CHARS


def test_default_header():
    captured: list[dict] = []

    with (
        patch(
            "decepticon.tools.interaction.scope_amendment.get_stream_writer",
            return_value=lambda evt: captured.append(evt),
        ),
        patch(
            "decepticon.tools.interaction.scope_amendment.interrupt",
            return_value="Approve — add to scope",
        ),
    ):
        _invoke()

    assert captured[0]["header"] == "Scope Amendment"
