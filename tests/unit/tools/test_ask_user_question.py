"""Unit tests for ``decepticon.tools.interaction.ask_user_question``."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from decepticon.tools.interaction import ask_user_question

# Pydantic constraints expressed in the tool signature; mirrored here so the
# tests document the contract without re-importing private constants.
HEADER_MAX_CHARS = 12
MAX_OPTIONS = 5


def _two_options() -> list[dict[str, str]]:
    return [
        {"label": "Yes", "description": "Approve"},
        {"label": "No", "description": "Reject"},
    ]


def _invoke(**overrides):
    """Invoke the @tool wrapper with sane defaults; ``overrides`` replace fields.

    Tools that declare ``InjectedToolCallId`` require a full ToolCall envelope,
    not a bare args dict — LangChain validates this at the wrapper layer and
    wraps the return value in a ``ToolMessage``. Returns the unwrapped content
    so tests can assert on the agent-visible payload directly.
    """
    args: dict = {
        "question": "Pick one",
        "header": "Pick",
        "options": _two_options(),
        "multi_select": False,
        "allow_other": False,
    }
    tool_call_id = overrides.pop("tool_call_id", "tc_1")
    args.update(overrides)
    result = ask_user_question.invoke(
        {
            "args": args,
            "name": "ask_user_question",
            "type": "tool_call",
            "id": tool_call_id,
        }
    )
    # ToolNode produces a ToolMessage wrapping the raw return value; tests want
    # the underlying content for verification.
    return getattr(result, "content", result)


def test_emits_custom_event_with_id_and_payload():
    captured: list[dict] = []

    def fake_writer(event: dict) -> None:
        captured.append(event)

    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=fake_writer,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="Yes",
        ),
    ):
        result = _invoke()

    assert result == "Yes"
    assert len(captured) == 1
    event = captured[0]
    assert event["type"] == "ask_user_question"
    assert event["agent"] == "soundwave"
    assert event["id"] == "tc_1"
    assert event["question"] == "Pick one"
    assert event["header"] == "Pick"
    assert event["options"] == _two_options()
    assert event["multi_select"] is False
    assert event["allow_other"] is False


def test_returns_interrupt_value_verbatim_for_single_select():
    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="No",
        ),
    ):
        assert _invoke() == "No"


def test_returns_list_verbatim_for_multi_select():
    chosen = ["Yes", "No"]
    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value=chosen,
        ),
    ):
        assert _invoke(multi_select=True) == chosen


def test_returns_free_text_when_allow_other_selected():
    typed = "Custom answer from operator"
    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value=typed,
        ),
    ):
        assert _invoke(allow_other=True) == typed


def test_skips_writer_when_outside_graph_context():
    """get_stream_writer raises outside a graph; the tool must continue gracefully."""

    def raising():
        raise RuntimeError("not in a graph context")

    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            side_effect=raising,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="Yes",
        ),
    ):
        # Should not raise; writer is best-effort.
        assert _invoke() == "Yes"


def test_rejects_header_longer_than_max():
    too_long = "X" * (HEADER_MAX_CHARS + 1)
    with patch(
        "decepticon.tools.interaction.ask_user.interrupt",
        return_value="Yes",
    ):
        with pytest.raises(ValidationError):
            _invoke(header=too_long)


def test_accepts_empty_options():
    """The tool now allows zero options so the operator can answer free-form
    via the Other fallback; a single option is also valid."""
    with patch(
        "decepticon.tools.interaction.ask_user.interrupt",
        return_value="typed answer",
    ):
        assert _invoke(options=[], allow_other=True) == "typed answer"
        assert _invoke(options=[{"label": "Solo", "description": "only one"}]) == "typed answer"


def test_rejects_too_many_options():
    too_many = [{"label": f"L{i}", "description": f"D{i}"} for i in range(MAX_OPTIONS + 1)]
    with patch(
        "decepticon.tools.interaction.ask_user.interrupt",
        return_value="Yes",
    ):
        with pytest.raises(ValidationError):
            _invoke(options=too_many)


def test_accepts_max_option_counts():
    """Boundary check — the upper limit MAX_OPTIONS must remain valid."""
    boundary_max = [{"label": f"L{i}", "description": f"D{i}"} for i in range(MAX_OPTIONS)]
    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="L0",
        ),
    ):
        assert _invoke(options=boundary_max) == "L0"


def test_rejects_option_without_label_or_description():
    with patch(
        "decepticon.tools.interaction.ask_user.interrupt",
        return_value="Yes",
    ):
        bad = [
            {"label": "A", "description": "ok"},
            {"label": "B"},  # missing description
        ]
        with pytest.raises(ValidationError):
            _invoke(options=bad)


def test_rejects_option_with_extra_fields():
    """extra='forbid' on QuestionOption keeps the schema strict for the LLM."""
    with patch(
        "decepticon.tools.interaction.ask_user.interrupt",
        return_value="Yes",
    ):
        bad = [
            {"label": "A", "description": "ok", "value": "extra"},
            {"label": "B", "description": "ok"},
        ]
        with pytest.raises(ValidationError):
            _invoke(options=bad)
