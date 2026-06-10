"""Unit tests for the GuidanceMiddleware."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import SystemMessage

from decepticon.middleware.guidance import GuidanceMiddleware


class MockRequest:
    def __init__(self, state: dict, system_message: SystemMessage | None = None) -> None:
        self.state = state
        self.system_message = system_message

    def override(self, system_message: SystemMessage) -> MockRequest:
        return MockRequest(self.state, system_message)


def test_guidance_no_inbox(tmp_path: Path) -> None:
    mw = GuidanceMiddleware()
    state = {"workspace_path": str(tmp_path)}
    req = MockRequest(state, SystemMessage(content="Hello"))

    res = mw._inject(req)
    assert res.system_message.content == "Hello"


def test_guidance_inbox_drained_and_cursor_updated(tmp_path: Path) -> None:
    mw = GuidanceMiddleware()
    state = {"workspace_path": str(tmp_path)}

    guidance_dir = tmp_path / "guidance"
    guidance_dir.mkdir(parents=True, exist_ok=True)
    inbox = guidance_dir / "inbox.jsonl"
    cursor = guidance_dir / "inbox.cursor"

    # Write first line
    inbox.write_text(json.dumps({"text": "focus on target 1"}) + "\n", encoding="utf-8")

    req = MockRequest(state, SystemMessage(content=[{"type": "text", "text": "Base system"}]))
    res = mw._inject(req)

    # Content should include the guidance
    blocks = res.system_message.content_blocks
    assert len(blocks) == 2
    assert "focus on target 1" in blocks[1]["text"]
    assert "OPERATOR GUIDANCE" in blocks[1]["text"]

    # Cursor should exist and contain the offset
    assert cursor.exists()
    offset = int(cursor.read_text(encoding="utf-8").strip())
    assert offset > 0

    # Write a second line
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"text": "do not touch .15"}) + "\n")

    res2 = mw._inject(req)
    blocks2 = res2.system_message.content_blocks
    assert len(blocks2) == 2
    assert "focus on target 1" in blocks2[1]["text"]
    assert "do not touch .15" in blocks2[1]["text"]

    # Cursor offset should have increased
    new_offset = int(cursor.read_text(encoding="utf-8").strip())
    assert new_offset > offset
