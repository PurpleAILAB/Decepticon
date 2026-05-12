"""complete_engagement_planning — signal soundwave-to-decepticon handoff.

Soundwave calls this exactly once after RoE / CONOPS / Deconfliction Plan
have been written, validated, and saved to ``/workspace/plan/``. The
emitted custom event tells the CLI to switch its LangGraph assistant_id from
``soundwave`` to ``decepticon`` so the next operator message lands on the
operations agent without the operator restarting the CLI.

The tool is a pure boolean signal — it carries no slug or other metadata.
The launcher is the single source of truth for the engagement slug; clients
inject ``engagement_name``/``workspace_path`` via ``config.configurable`` on
every run, and EngagementContextMiddleware hydrates them into agent state.

Runtime boundary
----------------
complete_engagement_planning runs inside the LangGraph container, which does
NOT mount the operator engagement workspace. The workspace lives inside the
decepticon-sandbox container. All filesystem operations (validation of plan
docs, marker write) go through DockerSandbox so they land on the correct
container filesystem, where mtime ordering with roe.json / conops.json /
deconfliction.json is guaranteed consistent.
"""

from __future__ import annotations

import json
import shlex
from datetime import datetime, timezone
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.middleware.engagement import _configurable_from_runnable_config


def _safe_writer():
    try:
        return get_stream_writer()
    except Exception:
        return None


def _resolve_workspace() -> str:
    """Return the active engagement workspace path, falling back to /workspace."""
    configurable = _configurable_from_runnable_config()
    workspace = configurable.get("workspace_path")
    if isinstance(workspace, str) and workspace.strip():
        return workspace.strip()
    return "/workspace"


@tool
def complete_engagement_planning(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Any:
    """Signal that engagement planning is finished and hand off to Decepticon.

    Call this tool exactly once, after RoE, CONOPS, and the Deconfliction Plan
    have all been written under ``/workspace/plan/`` and validated against
    their schemas. The CLI will switch the active assistant to Decepticon and
    the operator's next message starts the operations phase.

    If any of the three plan documents is missing or not valid JSON, this tool
    returns an error string describing the problem — no handoff event is emitted
    and no marker is written. Fix the document and call this tool again.

    Returns:
        A confirmation string the LLM can include in its closing message,
        or an error string if validation failed.
    """
    workspace = _resolve_workspace()
    sandbox = DockerSandbox(container_name=load_config().docker.sandbox_container_name)

    # Validate all three plan documents before touching the marker.
    plan_docs = ["roe.json", "conops.json", "deconfliction.json"]
    for doc in plan_docs:
        path = f"{workspace}/plan/{doc}"
        results = sandbox.download_files([path])
        r = results[0]
        if r.error is not None:
            return (
                f"Planning incomplete: {doc} is missing from {workspace}/plan/. "
                "Write it before calling this tool."
            )
        assert r.content is not None
        try:
            json.loads(r.content)
        except (json.JSONDecodeError, ValueError) as exc:
            return (
                f"Planning incomplete: {doc} is not valid JSON — {exc}. "
                "Fix it before calling this tool."
            )

    q = shlex.quote(workspace)

    # Invalidate any prior marker before committing the new one so a stale
    # marker from a previous run or partial replan cannot survive.
    sandbox.execute(f"rm -f {q}/plan/.bundle_complete")

    # Build the marker body. Keep fields minimal — the marker's value is its
    # existence + the mtime ordering guarantee the Go launcher checks.
    body = json.dumps(
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": 1,
        },
        ensure_ascii=False,
    ).encode()

    # Atomic sandbox-side commit: upload a temp file then rename it in-place.
    # The mv is the atomic step — it is a POSIX rename on the sandbox's
    # filesystem (same fs as the three plan docs), so mtime is assigned by the
    # same clock.  The upload itself is not atomic but the launcher only gates
    # on the final marker path, so this is sufficient.
    tmp_path = f"{workspace}/plan/.bundle_complete.tmp"

    upload_results = sandbox.upload_files([(tmp_path, body)])
    if upload_results[0].error is not None:
        sandbox.execute(f"rm -f {q}/plan/.bundle_complete.tmp {q}/plan/.bundle_complete")
        return (
            "Planning documents validated but the marker could not be uploaded "
            "to the sandbox. Check that the sandbox container is running and "
            "retry this tool."
        )

    mv_result = sandbox.execute(f"mv -f {q}/plan/.bundle_complete.tmp {q}/plan/.bundle_complete")
    if mv_result.exit_code != 0:
        sandbox.execute(f"rm -f {q}/plan/.bundle_complete.tmp {q}/plan/.bundle_complete")
        return (
            f"Planning documents validated but marker commit failed "
            f"(mv exited {mv_result.exit_code}). Retry this tool."
        )

    # Only emit the handoff event after the marker is committed on disk.
    writer = _safe_writer()
    if writer is not None:
        writer(
            {
                "type": "engagement_ready",
                "agent": "soundwave",
                "id": tool_call_id,
            }
        )
    return (
        "Planning complete. The operator's next message will be routed to the "
        "Decepticon operations agent."
    )
