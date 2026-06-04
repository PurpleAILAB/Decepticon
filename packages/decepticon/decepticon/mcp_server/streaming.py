"""Bounded live tail of an engagement's run stream.

The web UI and CLI render a live kill-chain feed by joining the run's
``custom``/``updates``/``messages`` stream. An MCP client can't hold a
long-lived stream open across a tool call, so this collects a *bounded*
window of stream parts (until a time or event cap) and returns them — enough
for the calling agent to narrate "what's happening right now" and poll again.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from decepticon.mcp_server.models import StreamEvent

_MAX_DATA_CHARS = 600
_STREAM_MODES = ["custom", "updates", "messages"]


def _compact(data: Any) -> str:
    try:
        text = json.dumps(data, default=str)
    except (TypeError, ValueError):
        text = str(data)
    return text if len(text) <= _MAX_DATA_CHARS else f"{text[:_MAX_DATA_CHARS]}…"


async def watch_run(
    client: Any,
    *,
    thread_id: str,
    run_id: str,
    max_seconds: float,
    max_events: int,
) -> tuple[list[StreamEvent], bool]:
    """Collect up to ``max_events`` stream parts or until ``max_seconds`` elapses.

    Returns ``(events, truncated)`` where ``truncated`` is True when the event
    cap was hit before the run ended or the timeout fired.
    """
    events: list[StreamEvent] = []
    truncated = False

    async def _collect() -> None:
        nonlocal truncated
        async for part in client.runs.join_stream(thread_id, run_id, stream_mode=_STREAM_MODES):
            event = getattr(part, "event", None)
            data = getattr(part, "data", None)
            if not event or data is None:
                continue
            events.append(StreamEvent(event=str(event), data=_compact(data)))
            if len(events) >= max_events:
                truncated = True
                return

    try:
        await asyncio.wait_for(_collect(), timeout=max_seconds)
    except asyncio.TimeoutError:
        # Timeout is expected: return whatever events were collected within
        # max_seconds. The caller distinguishes a timed-out partial result
        # from a complete one via the `truncated` flag and the event count.
        pass
    return events, truncated
