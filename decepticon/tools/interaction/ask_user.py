"""ask_user_question — structured multiple-choice prompt for the operator.

Pauses the running graph via ``langgraph.types.interrupt`` and emits a
structured ``ask_user_question`` custom event so the CLI can render a picker.
The CLI resumes the run with ``Command(resume=<choice>)`` and the chosen
value flows back as the tool's return value.

Argument validation is delegated to Pydantic via the @tool's auto-generated
args_schema — the LLM sees the constraints as part of the tool signature so
no prose schema lives in the prompt. The deterministic ``InjectedToolCallId``
is included in the emitted event so the CLI can deduplicate the second
emission that LangGraph performs when ToolNode re-executes the tool body
after resume.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field


class QuestionOption(BaseModel):
    """One choice in a multiple-choice operator prompt."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        description=(
            "What the operator sees and what the tool returns when this option "
            "is picked. Mark the most common option's label with a trailing "
            "' (Recommended)' when applicable."
        )
    )
    description: str = Field(description="One-line clarifier shown under the label in the picker.")


def _safe_writer():
    """Return the LangGraph stream writer if running inside a graph context."""
    try:
        return get_stream_writer()
    except Exception:
        return None


@tool
def ask_user_question(
    question: str,
    header: Annotated[
        str,
        Field(
            max_length=12,
            description="Short label (≤12 chars) shown as the picker's compact chrome label.",
        ),
    ],
    options: Annotated[
        list[QuestionOption],
        Field(
            max_length=5,
            description=(
                "0–5 choices. Each entry needs a label (operator-facing, returned) "
                "and a description (one-line clarifier). Provide 2–4 plausible "
                "guesses even for open-ended questions; the operator picks one or "
                "types a custom answer via the Other fallback. Never include an "
                "'Other' option here — set allow_other=True instead. May be left "
                "empty when there is genuinely no useful guess to offer; the "
                "picker then just collects free-text via Other."
            ),
        ),
    ] = [],
    multi_select: bool = False,
    allow_other: bool = True,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Any:
    """Ask the human operator a structured multiple-choice question and wait for the answer.

    Use this for closed-form taxonomy decisions where the user picks from a
    short list (engagement type, attack class, scope window, target category).
    Do NOT use for open-ended narrative answers (organization name, free-form
    rules) — write those as plain prose questions and let the operator type
    a normal reply.

    Args:
        question: The full question text shown to the operator.
        header: ≤12-char label for the picker chrome.
        options: 2–5 entries, each ``{label, description}``.
        multi_select: If True, the operator may pick multiple options and the
            return value is ``list[str]``.
        allow_other: If True, the picker appends an ``Other`` entry that opens
            a free-text input. The operator's typed text is returned verbatim.
        tool_call_id: Injected by LangChain — used by the CLI as the dedup key
            because the tool body re-runs on resume.

    Returns:
        Single-select: the chosen option's ``label``.
        Multi-select: list of selected labels (selection order).
        Free text via ``Other``: the operator's typed string.
    """
    payload = {
        "type": "ask_user_question",
        "agent": "soundwave",
        "id": tool_call_id,
        "question": question,
        "header": header,
        "options": [opt.model_dump() for opt in options],
        "multi_select": multi_select,
        "allow_other": allow_other,
    }

    writer = _safe_writer()
    if writer is not None:
        writer(payload)

    return interrupt(payload)
