"""complete_engagement_planning — signal soundwave-to-decepticon handoff.

Soundwave calls this exactly once after RoE / CONOPS / Deconfliction Plan
have been written, validated, and saved to ``/workspace/plan/``. The
emitted custom event tells the CLI to switch its LangGraph assistant_id from
``soundwave`` to ``decepticon`` so the next operator message lands on the
operations agent without the operator restarting the CLI.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer
from pydantic import Field


def _safe_writer():
    try:
        return get_stream_writer()
    except Exception:
        return None


@tool
def complete_engagement_planning(
    engagement_name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            description=(
                "Slug of the engagement whose planning bundle is now complete "
                "(matches the workspace directory under /workspace/)."
            ),
        ),
    ],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Any:
    """Signal that engagement planning is finished and hand off to Decepticon.

    Call this tool exactly once, after RoE, CONOPS, and the Deconfliction Plan
    have all been written under ``/workspace/plan/`` and
    validated against their schemas. The CLI will switch the active assistant
    to Decepticon and the operator's next message starts the operations
    phase.

    Args:
        engagement_name: The workspace slug. Must match the directory the
            planning documents were written to.

    Returns:
        A confirmation string the LLM can include in its closing message.
    """
    writer = _safe_writer()
    if writer is not None:
        writer(
            {
                "type": "engagement_ready",
                "agent": "soundwave",
                "id": tool_call_id,
                "engagement": engagement_name,
            }
        )
    return (
        f"Planning complete for engagement '{engagement_name}'. "
        "The operator's next message will be routed to the Decepticon "
        "operations agent."
    )
