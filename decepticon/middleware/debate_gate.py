"""DebateGateMiddleware — nudge the verifier to debate before promotion.

The *hard* enforcement lives in the ``validate_finding`` tool itself: it
returns ``promotion: blocked`` for a CRITICAL/HIGH finding that has not
cleared an adversarial debate. This middleware is the UX layer — when it
sees a blocked result it appends an explicit self-correction instruction
to the tool message so the agent calls ``debate_finding`` and retries
without burning a turn re-discovering the rule.

Installed only on the ``verifier`` role; the slot factory self-skips when
debate is globally disabled (``DECEPTICON_DEBATE=off``).
"""

from __future__ import annotations

import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

_GUIDANCE = (
    "\n\n[debate-gate] This finding was NOT promoted. Before re-running "
    "validate_finding, call debate_finding(vuln_id, finding_summary, "
    "poc_evidence) to cross-examine it with an independent cross-family "
    "model. If the debate verdict is 'refuted', do NOT retry — revisit the "
    "PoC or strengthen the negative control instead."
)


class DebateGateMiddleware(AgentMiddleware):
    """Annotate blocked ``validate_finding`` results with a recovery hint."""

    def wrap_tool_call(self, request, handler):  # type: ignore[override]
        return self._annotate(request, handler(request))

    async def awrap_tool_call(self, request, handler):  # type: ignore[override]
        return self._annotate(request, await handler(request))

    @staticmethod
    def _annotate(request, result):
        if request.tool_call.get("name") != "validate_finding":
            return result
        content = getattr(result, "content", None)
        if not isinstance(content, str) or '"promotion"' not in content:
            return result
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            return result
        if data.get("promotion") != "blocked":
            return result
        if isinstance(result, ToolMessage):
            return result.model_copy(update={"content": content + _GUIDANCE})
        return result
