"""complete_engagement_planning — write plan files and signal handoff to Decepticon.

Soundwave calls this after authoring RoE / CONOPS / Deconfliction Plan.
Passes the documents as ``plan_documents`` (a dict mapping filenames to
JSON content strings); the tool writes them to the engagement's plan
directory and emits the ``engagement_ready`` custom event so the CLI can
switch its LangGraph assistant_id from ``soundwave`` to ``decepticon``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer


def _safe_writer():
    try:
        return get_stream_writer()
    except Exception:
        return None


def _resolve_plan_dir(config: RunnableConfig | None) -> Path | None:
    workspace_path = None
    engagement_id = None

    if config:
        configurable = config.get("configurable") or {}
        workspace_path = configurable.get("workspace_path")
        engagement_id = (
            configurable.get("engagement_id") or configurable.get("engagement_name")
        )
        # Derive engagement_id from thread_id (gateway sets them to be the same minus dashes)
        thread_id = configurable.get("thread_id")
        if not engagement_id and thread_id:
            engagement_id = thread_id.replace("-", "")

    if workspace_path:
        return Path(workspace_path) / "plan"

    parent = os.environ.get("DECEPTICON_WORKSPACE_PATH") or os.environ.get("DECEPTICON_WORKSPACE")
    if parent and engagement_id:
        return Path(parent) / engagement_id / "plan"

    return None


@tool
def complete_engagement_planning(
    plan_documents: Annotated[
        dict[str, str],
        "Dict mapping filenames (e.g. 'roe.json') to JSON content strings. "
        "Must include roe.json, conops.json, deconfliction.json."
    ],
    config: Annotated[RunnableConfig, "Injected."] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Any:
    """Write plan documents to the engagement's plan/ directory and signal handoff.

    Pass a dict of {filename: json_string}. The tool writes them under
    the plan directory and emits the engagement_ready event.

    Returns:
        A confirmation string with the list of files written.
    """
    plan_dir = _resolve_plan_dir(config)
    if not plan_dir:
        return "ERROR: could not determine plan directory. workspace_path/engagement_id not in config or env."

    plan_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for name, content in plan_documents.items():
        safe_name = os.path.basename(name)
        if not safe_name.endswith(".json"):
            continue
        target = plan_dir / safe_name
        try:
            parsed = json.loads(content)
            target.write_text(json.dumps(parsed, indent=2))
            written.append(safe_name)
        except json.JSONDecodeError as exc:
            return f"ERROR: {safe_name} is not valid JSON: {exc}"

    writer = _safe_writer()
    if writer is not None:
        writer(
            {
                "type": "engagement_ready",
                "agent": "soundwave",
                "id": tool_call_id,
                "files": written,
            }
        )

    return (
        f"Planning complete. Wrote {len(written)} files ({', '.join(written)}). "
        "The operator's next message will be routed to the Decepticon operations agent."
    )
