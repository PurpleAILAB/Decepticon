"""request_scope_amendment — operator approval for scope-expansion opportunities.

Mid-engagement, recon and exploitation regularly surface assets that sit
OUTSIDE the written RoE but could chain into impact: a sibling domain on
shared infrastructure, a dangling subdomain eligible for takeover, a
third-party admin portal bearing the client's brand. Before this tool
existed, those opportunities were either silently skipped (surface lost)
or silently tested (legal exposure). This tool gives the orchestrator a
structured channel: pause the graph, present the opportunity with its
chain rationale, and let the operator approve, deny, or amend (free-text
constraints via the picker's Other option).

The emitted event deliberately reuses the ``ask_user_question`` payload
contract so the existing CLI / Web pickers render it without client
changes; the extra ``asset`` / ``proposed_action`` / ``rationale`` fields
are additive context for clients that choose to render them.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from decepticon.tools.interaction.ask_user import (
    _strip_recommended_suffix,
    _truncate_header,
)

DEFAULT_HEADER = "Scope Amendment"


def _safe_writer():
    """Return the LangGraph stream writer if running inside a graph context."""
    try:
        return get_stream_writer()
    except Exception:
        return None


@tool
def request_scope_amendment(
    asset: Annotated[
        str, "The out-of-scope asset or class: domain, host, netblock, SaaS tenant, etc."
    ],
    proposed_action: Annotated[
        str,
        "What you want to do to it, concretely (e.g. 'passive DNS + HTTP GET only', "
        "'claim the dangling CloudFront hostname', 'port scan top-10000').",
    ],
    rationale: Annotated[
        str,
        "Why this is worth the operator's attention — the chain hypothesis: what "
        "this asset could lead to and which in-scope objective it serves.",
    ],
    header: Annotated[str, "Short picker label (≤60 chars)."] = DEFAULT_HEADER,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Any:
    """Ask the operator to approve testing an out-of-scope asset.

    Use ONLY when all of these hold:
    - The asset is OUTSIDE the written scope in plan/roe.json (assets inside
      the boundary need no approval — test them).
    - Discovery during the engagement linked it to the target (shared infra,
      brand, cert, credential, code reference) — not speculation.
    - You can articulate the chain: what testing it might unlock.

    Returns the operator's decision verbatim: an option label
    ("Approve — add to scope" / "Deny — keep out of scope") or free text
    typed via Other (typically an approval with constraints — treat the
    text as binding). On approval, record the amendment in the engagement
    notes before dispatching any work against the asset.
    """
    question = (
        f"Scope expansion opportunity discovered mid-engagement.\n\n"
        f"Asset (currently OUT of scope): {asset}\n\n"
        f"Proposed action: {proposed_action}\n\n"
        f"Chain rationale: {rationale}\n\n"
        f"Approve adding this asset to the engagement scope?"
    )
    payload = {
        "type": "ask_user_question",
        "agent": "decepticon",
        "id": tool_call_id,
        "question": question,
        "header": _truncate_header(header),
        "options": [
            {
                "label": "Approve — add to scope",
                "description": "Asset becomes in-scope for the stated action; record the amendment.",
            },
            {
                "label": "Deny — keep out of scope",
                "description": "Do not touch the asset; record the opportunity as declined.",
            },
        ],
        "multi_select": False,
        "allow_other": True,
        # Scope-amendment context — additive; pickers that only know the
        # base ask_user_question contract ignore these fields.
        "asset": asset,
        "proposed_action": proposed_action,
        "rationale": rationale,
    }

    writer = _safe_writer()
    if writer is not None:
        writer(payload)

    return _strip_recommended_suffix(interrupt(payload))
