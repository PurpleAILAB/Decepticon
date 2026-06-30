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

import ast
import json
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

HEADER_MAX_CHARS = 60
MAX_OPTIONS = 6
RECOMMENDED_SUFFIX = " (Recommended)"


def _strip_recommended_suffix(value: Any) -> Any:
    """Strip the ``" (Recommended)"`` UI marker from operator answers.

    Option labels surface the marker so the operator sees which choice the
    agent recommends in the picker; the marker is purely a display hint and
    must never reach the agent's tool-result content. Without stripping, the
    model treats the marker as part of the answer (e.g. ``"Internal Network
    Audit (Recommended)"`` becomes the engagement name), decides the
    parenthetical meta-text is not a valid value, and re-asks the same
    question — the Soundwave interview loop bug from issue #328.

    Operates on single-select strings and multi-select string lists; any
    other shape is returned unchanged.
    """

    def _strip(v: Any) -> Any:
        if isinstance(v, str) and v.endswith(RECOMMENDED_SUFFIX):
            return v[: -len(RECOMMENDED_SUFFIX)]
        return v

    if isinstance(value, list):
        return [_strip(v) for v in value]
    return _strip(value)


def _coerce_options_list(value: Any) -> list[Any]:
    """Normalize common local-model shapes for ``options``."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, str):
        return []

    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (json.JSONDecodeError, ValueError, SyntaxError, TypeError, MemoryError):
            continue
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]

    try:
        cleaned = value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _truncate_header(value: Any) -> Any:
    if isinstance(value, str) and len(value) > HEADER_MAX_CHARS:
        return value[:HEADER_MAX_CHARS]
    return value


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
        BeforeValidator(_truncate_header),
        Field(
            max_length=HEADER_MAX_CHARS,
            description="Short label (≤60 chars) shown as the picker's compact chrome label.",
        ),
    ],
    options: Annotated[
        list[QuestionOption],
        BeforeValidator(_coerce_options_list),
        Field(
            max_length=MAX_OPTIONS,
            description=(
                "0–6 choices. Each entry needs a label (operator-facing, returned) "
                "and a description (one-line clarifier). Provide 2–6 plausible "
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
        header: ≤60-char label for the picker chrome.
        options: 2–6 entries, each ``{label, description}``.
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

    return _strip_recommended_suffix(interrupt(payload))
