"""``decepticon-cli export-transcript`` - render an engagement's event log.

Reads the append-only ``events.jsonl`` for one engagement and renders it as a
human-readable Markdown transcript. The log lives at
``<workspace>/engagements/<engagement_id>/events.jsonl`` (see
:mod:`decepticon.runtime.event_log`); events are rendered in the order they
were appended.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decepticon.runtime.event_log import EngagementEvent, EventType, read_events

EXIT_OK = 0
EXIT_NOT_FOUND = 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="decepticon-cli export-transcript",
        description="Render an engagement's event log as a Markdown transcript.",
    )
    p.add_argument(
        "engagement_id",
        help="Engagement identifier whose events.jsonl should be rendered.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the transcript to this file. Defaults to stdout.",
    )
    p.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help=(
            "Engagement workspace root. Defaults to $DECEPTICON_WORKSPACE "
            "when set, otherwise the current directory."
        ),
    )
    return p


def _resolve_workspace(arg_value: Path | None) -> Path:
    if arg_value is not None:
        return arg_value
    env = os.environ.get("DECEPTICON_WORKSPACE")
    return Path(env) if env else Path(".")


def _events_path(workspace: Path, engagement_id: str) -> Path:
    return workspace / "engagements" / engagement_id / "events.jsonl"


def _format_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OverflowError, OSError, ValueError):
        return str(ts)


def _as_json_block(value: Any) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str, sort_keys=True)
    return f"```json\n{text}\n```"


def _payload(event: EngagementEvent) -> dict[str, Any]:
    """Return the event payload as a dict, tolerating malformed (non-dict) payloads.

    ``read_events`` yields events for any well-formed JSON line, so a corrupted
    or hand-edited log may carry a non-dict ``payload`` (e.g. a list). Coerce
    such payloads to an empty dict so a single bad line cannot crash the export.
    """
    return event.payload if isinstance(event.payload, dict) else {}


def _render_engagement_start(event: EngagementEvent) -> list[str]:
    lines = [f"## Engagement started — {_format_ts(event.ts)}"]
    payload = _payload(event)
    name = payload.get("name") or payload.get("engagement") or payload.get("target")
    if name:
        lines.append(f"- **engagement:** {name}")
    extra = {k: v for k, v in payload.items() if k not in {"name", "engagement", "target"}}
    if name is None and payload:
        extra = dict(payload)
    if extra:
        lines.append(_as_json_block(extra))
    return lines


def _render_engagement_end(event: EngagementEvent) -> list[str]:
    lines = [f"## Engagement ended — {_format_ts(event.ts)}"]
    if event.payload:
        lines.append(_as_json_block(event.payload))
    return lines


def _render_agent_turn(event: EngagementEvent) -> list[str]:
    name = event.agent or "agent"
    lines = [f"### {name} — {_format_ts(event.ts)}"]
    payload = _payload(event)
    content = payload.get("content") or payload.get("message") or payload.get("text")
    if content:
        lines.append(str(content))
    else:
        remainder = {k: v for k, v in payload.items() if k not in {"content", "message", "text"}}
        if remainder:
            lines.append(_as_json_block(remainder))
    return lines


def _render_tool_call(event: EngagementEvent) -> list[str]:
    payload = _payload(event)
    tool = payload.get("tool") or "tool"
    lines = [f"#### Tool call: `{tool}` — {_format_ts(event.ts)}"]
    args = payload.get("args")
    if args:
        lines.append("Arguments:")
        lines.append(_as_json_block(args))
    return lines


def _render_tool_result(event: EngagementEvent) -> list[str]:
    payload = _payload(event)
    tool = payload.get("tool") or "tool"
    lines = [f"#### Tool result: `{tool}` — {_format_ts(event.ts)}"]
    if "result" in payload:
        result: Any = payload["result"]
    else:
        result = {k: v for k, v in payload.items() if k != "tool"}
    if result not in (None, {}):
        lines.append(_as_json_block(result))
    return lines


def _render_generic(event: EngagementEvent) -> list[str]:
    label = event.type or "event"
    suffix = f" ({event.agent})" if event.agent else ""
    lines = [f"### {label}{suffix} — {_format_ts(event.ts)}"]
    if event.payload:
        lines.append(_as_json_block(event.payload))
    return lines


_RENDERERS = {
    EventType.ENGAGEMENT_START.value: _render_engagement_start,
    EventType.ENGAGEMENT_END.value: _render_engagement_end,
    EventType.AGENT_TURN.value: _render_agent_turn,
    EventType.TOOL_CALL.value: _render_tool_call,
    EventType.TOOL_RESULT.value: _render_tool_result,
}


def render_transcript(engagement_id: str, events: list[EngagementEvent]) -> str:
    """Render ``events`` (in order) as a Markdown transcript document."""
    blocks: list[str] = [f"# Engagement transcript: {engagement_id}"]
    for event in events:
        renderer = _RENDERERS.get(event.type, _render_generic)
        blocks.append("\n".join(renderer(event)))
    return "\n\n".join(blocks) + "\n"


def _write_stdout(text: str) -> None:
    """Emit ``text`` on stdout as UTF-8, independent of the locale encoding.

    The transcript intentionally contains non-ASCII characters (em dashes,
    ``ensure_ascii=False`` JSON), which a plain ``sys.stdout.write`` would fail
    to encode under an ASCII/``C`` locale or a legacy Windows code page. Writing
    through the underlying binary buffer keeps stdout consistent with the
    UTF-8 file output above.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        sys.stdout.flush()
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    workspace = _resolve_workspace(args.workspace)
    path = _events_path(workspace, args.engagement_id)
    if not path.exists():
        print(f"error: engagement event log not found: {path}", file=sys.stderr)
        return EXIT_NOT_FOUND

    events = list(read_events(path))
    transcript = render_transcript(args.engagement_id, events)

    output: Path | None = args.output
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(transcript, encoding="utf-8")
    else:
        _write_stdout(transcript)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
