"""AgentStateMiddleware — extends agent state with per-agent scratch keys.

Pairs with :mod:`decepticon.tools.agentstate.tools`. The middleware adds
three keys to ``AgentState`` so the scratch tools have somewhere to read
and write:

* ``agent_todo``     — list of ``{id, item, status, ts}`` dicts
* ``agent_notes``    — list of ``{ts, note}`` dicts
* ``agent_thinking`` — list of ``{ts, thought}`` dicts

All three are ``OmitFromInput`` — only the scratch tools mutate them, and
they are not part of the public input schema. The middleware's
``before_model`` hook injects a small system reminder so the LLM is aware
of the pending todos/notes without needing an explicit ``agent_todo_list``
call every turn (cheap context, fits in one paragraph).

Scope is intentionally per-agent: each agent that mounts this middleware
gets its own scratch state. Sharing across agents is the orchestrator's
job (it reads tool messages, not state keys).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, NotRequired

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import OmitFromInput
from langchain_core.messages import SystemMessage

log = logging.getLogger(__name__)


class AgentStateExtension(AgentState):
    """Mixin adding per-agent scratch keys to the standard AgentState."""

    agent_todo: Annotated[NotRequired[list[dict]], OmitFromInput]
    """Per-agent todo list — see :func:`decepticon.tools.agentstate.tools.agent_todo_add`."""

    agent_notes: Annotated[NotRequired[list[dict]], OmitFromInput]
    """Per-agent free-form memo store."""

    agent_thinking: Annotated[NotRequired[list[dict]], OmitFromInput]
    """Per-agent chain-of-thought log (no I/O, scratch only)."""


_REMINDER_HEADER = (
    "## Agent Scratch State\n"
    "You have per-agent scratch tools: ``agent_thinking``, ``agent_todo_add``, "
    "``agent_todo_complete``, ``agent_todo_list``, ``agent_note_add``, "
    "``agent_note_list``, ``agent_finish``. Use them to externalise plans + "
    "findings between turns."
)


def _safe_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _format_status_block(state: dict) -> str:
    """Render a compact status block with open todos + last note timestamp."""
    todos = _safe_list(state.get("agent_todo"))
    notes = _safe_list(state.get("agent_notes"))
    thoughts = _safe_list(state.get("agent_thinking"))
    open_todos = [t for t in todos if t.get("status") != "done"]
    if not (todos or notes or thoughts):
        return ""
    lines: list[str] = ["", "### Current scratch:"]
    if open_todos:
        lines.append(f"- {len(open_todos)} open todo(s):")
        for t in open_todos[:8]:
            lines.append(f"  - #{t.get('id')} {t.get('item')}")
        if len(open_todos) > 8:
            lines.append(f"  - … +{len(open_todos) - 8} more")
    elif todos:
        lines.append(f"- {len(todos)} todo(s), all done")
    if notes:
        lines.append(f"- {len(notes)} note(s) recorded — call ``agent_note_list`` to read")
    if thoughts:
        lines.append(f"- {len(thoughts)} thought entr(ies) recorded")
    return "\n".join(lines)


class AgentStateMiddleware(AgentMiddleware):
    """Extend AgentState with scratch keys and inject a status reminder.

    Mount this on any agent that uses the agent_state tools. The state
    extension is automatic (LangGraph merges the schema), and the
    ``before_model`` hook prepends a system reminder summarising the
    current scratch state so the LLM doesn't repeatedly call
    ``agent_todo_list`` just to remember its plan.
    """

    state_schema = AgentStateExtension

    def __init__(self, *, inject_reminder: bool = True) -> None:
        """Initialise the middleware.

        Args:
          inject_reminder: When ``True`` (default), prepend a status block
            to the system message every turn. Set ``False`` to keep the
            state schema extension without the reminder side-effect (e.g.
            when the agent prompt already enumerates the scratch tools).
        """
        super().__init__()
        self._inject_reminder = inject_reminder

    def before_model(self, state, runtime):  # type: ignore[override]  # noqa: ARG002
        if not self._inject_reminder:
            return None
        status = _format_status_block(state)
        if not status:
            return None
        # Prepend system reminder. The standard pattern in this repo (see
        # OPPLANMiddleware) emits a SystemMessage; LangChain dedupes so a
        # repeated reminder doesn't bloat the chat log.
        messages = list(state.get("messages", []))
        messages.insert(0, SystemMessage(content=_REMINDER_HEADER + "\n" + status))
        return {"messages": messages}
