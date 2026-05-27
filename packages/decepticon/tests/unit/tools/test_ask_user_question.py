"""Unit tests for ``decepticon.tools.interaction.ask_user_question``."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from decepticon.tools.interaction import ask_user_question

# Pydantic constraints expressed in the tool signature; mirrored here so the
# tests document the contract without re-importing private constants.
HEADER_MAX_CHARS = 60
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


def test_truncates_header_longer_than_max():
    captured: list[dict] = []
    too_long = "X" * (HEADER_MAX_CHARS + 10)

    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda event: captured.append(event),
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="Yes",
        ),
    ):
        assert _invoke(header=too_long) == "Yes"

    assert captured[0]["header"] == "X" * HEADER_MAX_CHARS


def test_coerces_options_json_string_from_local_models():
    options = '[{"label":"External Web (Recommended)","description":"Public website"}]'
    captured: list[dict] = []

    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda event: captured.append(event),
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="External Web (Recommended)",
        ),
    ):
        # The emitted event preserves the operator-facing label (with the
        # marker) so the picker can render the recommendation hint, but the
        # tool return value has the marker stripped — see issue #328.
        assert _invoke(options=options) == "External Web"

    assert captured[0]["options"] == [
        {"label": "External Web (Recommended)", "description": "Public website"}
    ]


def test_coerces_options_python_literal_string_from_local_models():
    options = "[{'label': 'Recon', 'description': 'Surface level\\nonly'}]"
    captured: list[dict] = []

    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda event: captured.append(event),
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="Recon",
        ),
    ):
        assert _invoke(options=options) == "Recon"

    assert captured[0]["options"] == [{"label": "Recon", "description": "Surface level\nonly"}]


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


def test_strips_recommended_suffix_from_single_select_return():
    """Regression for issue #328 — the picker's ' (Recommended)' UI marker
    must never reach the agent's tool result. Without stripping, the model
    treats the parenthetical meta-text as part of the answer, rejects it,
    and locks the Soundwave interview in a loop."""
    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value="Internal Network Audit (Recommended)",
        ),
    ):
        assert _invoke() == "Internal Network Audit"


def test_strips_recommended_suffix_from_multi_select_return():
    """Multi-select returns a list of labels; every entry must be stripped."""
    chosen = ["Recon (Recommended)", "Exploitation", "Post-exploit (Recommended)"]
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
        assert _invoke(multi_select=True) == ["Recon", "Exploitation", "Post-exploit"]


def test_preserves_free_text_without_recommended_suffix():
    """Operator-typed answers via the Other fallback never carry the marker;
    the stripper is a no-op for them."""
    typed = "Acme Q1-2026 Adversary Sim"
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


def test_does_not_strip_recommended_when_not_a_trailing_suffix():
    """Only the trailing marker is a UI hint. A label that genuinely embeds
    ' (Recommended)' mid-string is not a picker artifact and must survive
    intact — the strip is suffix-only, not substring-wide."""
    embedded = "Mode (Recommended) for review"
    with (
        patch(
            "decepticon.tools.interaction.ask_user.get_stream_writer",
            return_value=lambda _evt: None,
        ),
        patch(
            "decepticon.tools.interaction.ask_user.interrupt",
            return_value=embedded,
        ),
    ):
        assert _invoke() == embedded


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
