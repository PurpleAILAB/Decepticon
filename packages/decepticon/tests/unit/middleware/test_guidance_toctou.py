"""Regression tests pinning the TOCTOU fix in GuidanceMiddleware (supersedes #636).

Original code used `if path.exists(): path.open(...)` on inbox + cursor,
opening a measurable race window. Fixed to EAFP (try / except FileNotFoundError).
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import SystemMessage

from decepticon.middleware.guidance import GuidanceMiddleware


class _MockRequest:
    def __init__(self, state: dict, system_message: SystemMessage | None = None) -> None:
        self.state = state
        self.system_message = system_message

    def override(self, system_message: SystemMessage) -> "_MockRequest":
        return _MockRequest(self.state, system_message)


def test_redamon_classifier_no_toctou_race(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """No `Path.exists()` is called on inbox/cursor in the read path (TOCTOU window: 1 stat -> 0)."""
    mw = GuidanceMiddleware()
    state = {"workspace_path": str(tmp_path)}
    guidance_dir = tmp_path / "guidance"
    guidance_dir.mkdir(parents=True, exist_ok=True)
    (guidance_dir / "inbox.jsonl").write_text(
        json.dumps({"text": "focus on .14"}) + "\n", encoding="utf-8"
    )

    exists_calls: list[str] = []
    original_exists = Path.exists

    def tracked_exists(self: Path) -> bool:
        exists_calls.append(str(self))
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", tracked_exists)
    mw._update_guidance(state)

    guidance_calls = [c for c in exists_calls if "guidance" in c]
    assert guidance_calls == [], (
        f"TOCTOU race: read path must use EAFP, not Path.exists() pre-checks. "
        f"Unexpected calls: {guidance_calls}"
    )
    assert mw._guidance_lines == ["focus on .14"]


def test_redamon_classifier_missing_inbox_silent(tmp_path: Path) -> None:
    """Missing inbox must not raise — EAFP swallows FileNotFoundError."""
    mw = GuidanceMiddleware()
    mw._update_guidance({"workspace_path": str(tmp_path)})
    assert mw._guidance_lines == []
