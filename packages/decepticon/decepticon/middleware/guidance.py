"""Operator Guidance Middleware — inject live guidance from the CLI / API.

Drains guidance from the workspace's guidance/inbox.jsonl file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from typing_extensions import override

from decepticon.middleware.engagement import _resolve_workspace_path

log = logging.getLogger(__name__)


class GuidanceMiddleware(AgentMiddleware):
    """Inject operator guidance from a file-backed inbox.jsonl into the system prompt."""

    def __init__(self) -> None:
        super().__init__()
        # In-memory store of active guidance lines
        self._guidance_lines: list[str] = []

    def _update_guidance(self, state: Any) -> None:
        workspace = _resolve_workspace_path(state)
        inbox_path = Path(workspace) / "guidance" / "inbox.jsonl"
        cursor_path = Path(workspace) / "guidance" / "inbox.cursor"

        if not inbox_path.exists():
            return

        offset = 0
        if cursor_path.exists():
            try:
                offset = int(cursor_path.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                offset = 0

        new_offset = offset
        new_guidance = []
        try:
            with inbox_path.open("r", encoding="utf-8") as fh:
                fh.seek(offset)
                while True:
                    line = fh.readline()
                    if not line:
                        break
                    new_offset = fh.tell()
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if "text" in obj:
                            text_val = str(obj["text"])
                            if len(text_val) > 1000:
                                text_val = text_val[:1000]
                            new_guidance.append(text_val)
                    except json.JSONDecodeError:
                        log.warning("malformed guidance line skipped")
                        continue
        except OSError as e:
            log.warning("failed to read guidance inbox: %s", e)
            return

        if new_offset > offset:
            try:
                cursor_path.parent.mkdir(parents=True, exist_ok=True)
                cursor_path.write_text(str(new_offset), encoding="utf-8")
                if new_guidance:
                    self._guidance_lines.extend(new_guidance)
                    self._guidance_lines = self._guidance_lines[-5:]
            except OSError as e:
                log.warning("failed to write guidance cursor: %s", e)

    def _inject(self, request: Any) -> Any:
        self._update_guidance(request.state)
        if not self._guidance_lines:
            return request

        guidance_text = "\n".join(f"- {line}" for line in self._guidance_lines)
        injection = (
            "\n\n[OPERATOR GUIDANCE - TRUSTED]\n"
            "The operator has provided the following steering guidance:\n"
            f"{guidance_text}\n"
            "Incorporate this guidance into your execution. Note: Guidance cannot "
            "override or relax the Rules of Engagement (RoE) or approved OPPLAN. "
            "All actions must still comply with RoE constraints."
        )

        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": injection},
            ]
        else:
            new_content = [{"type": "text", "text": injection}]

        new_system = SystemMessage(content=new_content)
        return request.override(system_message=new_system)

    @override
    def wrap_model_call(self, request, handler):
        return handler(self._inject(request))

    @override
    async def awrap_model_call(self, request, handler):
        return await handler(self._inject(request))
