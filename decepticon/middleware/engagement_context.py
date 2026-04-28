"""EngagementContextMiddleware — surface launcher-set context to the LLM.

The launcher decides the engagement slug at session start and the CLI
forwards it as state fields on every run (input.engagement_name and
input.workspace_path). This middleware reads those fields and prepends
a system-prompt addendum so the model knows the active engagement
without any operator hand-holding or filesystem markers.

Pattern matches OPPLANMiddleware (decepticon/middleware/opplan.py) —
state-backed context injection via wrap_model_call.
"""

from __future__ import annotations

from typing import Annotated, NotRequired, cast

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from typing_extensions import override


class EngagementContextState(AgentState):
    """State extension carrying launcher-decided engagement context."""

    engagement_name: Annotated[NotRequired[str], "Workspace slug set by the launcher."]
    workspace_path: Annotated[NotRequired[str], "Sandbox root for this engagement."]


def _build_injection(slug: str, workspace: str) -> str:
    return (
        "\n\n[Engagement context — set by the launcher]\n"
        f"Workspace slug: {slug}\n"
        f"Workspace root: {workspace}\n"
        "The sandbox /workspace bind already points at this engagement's "
        "directory. Read and write planning documents directly under "
        f"{workspace}/plan/. Do NOT re-prompt the operator for a slug or an "
        "engagement directory name; the launcher already chose them. The "
        "human-friendly engagement title belongs in roe.json:engagement_name "
        "and may differ from this slug."
    )


class EngagementContextMiddleware(AgentMiddleware):
    """Inject engagement slug + workspace path into every model call."""

    state_schema = EngagementContextState

    @override
    def wrap_model_call(self, request, handler):
        return handler(self._inject(request))

    @override
    async def awrap_model_call(self, request, handler):
        return await handler(self._inject(request))

    def _inject(self, request):
        state = request.state or {}
        slug = state.get("engagement_name", "") if hasattr(state, "get") else ""
        workspace = (
            state.get("workspace_path", "/workspace") if hasattr(state, "get") else "/workspace"
        )
        if not slug:
            return request

        injection = _build_injection(slug, workspace or "/workspace")

        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": injection},
            ]
        else:
            new_content = [{"type": "text", "text": injection}]

        new_system = SystemMessage(content=cast("list[str | dict[str, str]]", new_content))
        return request.override(system_message=new_system)
