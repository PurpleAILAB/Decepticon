"""Parse LangGraph ThreadState into agent-friendly transcript + engagement state.

Pure functions (no I/O) so they unit-test against representative state dicts.
The orchestrator transcript is the persisted narrative an external agent polls
to "watch" an engagement: human prompts, the coordinator's replies, and the
``task()`` delegations to specialist sub-agents with their results.
"""

from __future__ import annotations

import json
from typing import Any

from decepticon.mcp_server.models import EngagementState, Transcript, TranscriptMessage

_MAX_TEXT = 2000
_MAX_VALUE_CHARS = 2000
_ROLE_MAP = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}… (+{len(text) - limit} chars)"


def _content_text(content: Any) -> str:
    """Flatten message content (str or a list of content blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p)
    return ""


def _tool_call_label(call: dict[str, Any]) -> str:
    name = str(call.get("name", "tool"))
    args = call.get("args")
    if name == "task" and isinstance(args, dict):
        target = args.get("subagent_type") or args.get("subagent") or args.get("description")
        if target:
            return f"task({_truncate(str(target), 60)})"
    return name


def _to_message(index: int, raw: dict[str, Any]) -> TranscriptMessage:
    msg_type = str(raw.get("type", "ai"))
    tool_calls = [_tool_call_label(c) for c in raw.get("tool_calls", []) if isinstance(c, dict)]
    return TranscriptMessage(
        index=index,
        role=_ROLE_MAP.get(msg_type, msg_type),
        text=_truncate(_content_text(raw.get("content", "")), _MAX_TEXT),
        tool_calls=tool_calls,
        name=str(raw["name"]) if raw.get("name") else None,
    )


def _messages(state: Any) -> list[dict[str, Any]]:
    values = state.get("values") if isinstance(state, dict) else None
    if not isinstance(values, dict):
        return []
    messages = values.get("messages")
    return [m for m in messages if isinstance(m, dict)] if isinstance(messages, list) else []


def build_transcript(
    state: Any, *, thread_id: str, run_status: str, after_index: int, limit: int
) -> Transcript:
    """Build a transcript window starting at ``after_index`` (incremental polling)."""
    messages = _messages(state)
    total = len(messages)
    start = max(after_index, 0)
    window = messages[start : start + limit]
    parsed = [_to_message(start + offset, raw) for offset, raw in enumerate(window)]
    return Transcript(
        thread_id=thread_id,
        run_status=run_status,
        total=total,
        next_index=start + len(window),
        messages=parsed,
    )


def _compact_value(value: Any) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return _truncate(str(value), _MAX_VALUE_CHARS)
    if len(encoded) <= _MAX_VALUE_CHARS:
        return value
    return f"<{len(encoded)} chars omitted>"


def build_engagement_state(state: Any, *, thread_id: str, run_status: str) -> EngagementState:
    """Extract engagement context (OPPLAN / scope / phase) minus the message log."""
    values = state.get("values") if isinstance(state, dict) else None
    values = values if isinstance(values, dict) else {}
    name = values.get("engagement_name")
    context = {k: _compact_value(v) for k, v in values.items() if k != "messages"}
    return EngagementState(
        thread_id=thread_id,
        engagement_name=str(name) if name else None,
        run_status=run_status,
        message_count=len(_messages(state)),
        values=context,
    )
