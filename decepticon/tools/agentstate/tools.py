"""Per-agent state tool implementations.

Pattern mirrors :mod:`decepticon.tools.opplan` — tools return a
``langgraph.types.Command`` that updates the agent's state and emits a
``ToolMessage`` with a human-readable confirmation. State lives in
``AgentState`` extension keys (``agent_todo``, ``agent_notes``,
``agent_thinking``) injected via :class:`AgentStateMiddleware`.

Each tool is intentionally small — these are scratch primitives the LLM
uses to externalise its plan/notes between turns. They are not a
substitute for OPPLAN (engagement-wide objectives) or filesystem writes
(durable artefacts). When the agent finishes, ``agent_finish`` clears
the scratch and emits a final summary.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

log = logging.getLogger(__name__)

# Public registry — used by the per-agent middleware loader to surface
# these tools alongside the rest of the toolkit. ``finish`` is exposed
# under the ``agent_finish`` name to avoid colliding with the deepagents
# built-in ``finish`` (which is reserved for graph termination).
AGENT_STATE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "agent_thinking",
        "agent_todo_add",
        "agent_todo_complete",
        "agent_todo_list",
        "agent_note_add",
        "agent_note_list",
        "agent_finish",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_list(value: Any) -> list[dict]:
    """Return ``value`` as a list-of-dict, defensively coercing junk inputs."""
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


# ── thinking ──────────────────────────────────────────────────────────


@tool
def agent_thinking(
    thought: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Record a structured chain-of-thought entry.

    Use this when you want to externalise reasoning *before* taking action
    — the entry is appended to ``state['agent_thinking']`` so a later
    summariser can replay your decision trail. No I/O, no side effects.

    Args:
      thought: A free-form sentence or paragraph describing the next step,
        a hypothesis, or a constraint you've just discovered.
    """
    text = (thought or "").strip()
    if not text:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "thinking entry rejected: empty thought",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    log_list = _safe_list(state.get("agent_thinking"))
    log_list.append({"ts": _now(), "thought": text})
    return Command(
        update={
            "agent_thinking": log_list,
            "messages": [
                ToolMessage(
                    f"thinking #{len(log_list)} recorded ({len(text)} chars)",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


# ── todo ──────────────────────────────────────────────────────────────


@tool
def agent_todo_add(
    item: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Append a todo item to the per-agent scratch list.

    The item is stored as ``{id, item, status, ts}`` with ``status='open'``.
    Use ``agent_todo_complete(id=N)`` to mark it done.
    """
    text = (item or "").strip()
    if not text:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "todo rejected: empty item",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    todos = _safe_list(state.get("agent_todo"))
    new_id = (max((t.get("id", 0) for t in todos), default=0) or 0) + 1
    todos.append({"id": new_id, "item": text, "status": "open", "ts": _now()})
    return Command(
        update={
            "agent_todo": todos,
            "messages": [
                ToolMessage(
                    f"todo #{new_id} added: {text}",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def agent_todo_complete(
    todo_id: int,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Mark a todo entry done by its integer ``id``."""
    todos = _safe_list(state.get("agent_todo"))
    found = False
    for t in todos:
        if t.get("id") == todo_id:
            t["status"] = "done"
            t["completed_ts"] = _now()
            found = True
            break
    if not found:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"todo #{todo_id} not found",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    return Command(
        update={
            "agent_todo": todos,
            "messages": [
                ToolMessage(
                    f"todo #{todo_id} completed",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def agent_todo_list(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Render the current per-agent todo list as text."""
    todos = _safe_list(state.get("agent_todo"))
    if not todos:
        body = "(no todos)"
    else:
        lines = []
        for t in todos:
            mark = "x" if t.get("status") == "done" else " "
            lines.append(f"[{mark}] #{t.get('id')} — {t.get('item')}")
        body = "\n".join(lines)
    return Command(
        update={
            "messages": [
                ToolMessage(body, tool_call_id=tool_call_id),
            ]
        }
    )


# ── notes ─────────────────────────────────────────────────────────────


@tool
def agent_note_add(
    note: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Append a free-form memo to ``state['agent_notes']``.

    Notes are kept in insertion order. Use them for findings the orchestrator
    will summarise later, intermediate hypotheses, or context that should
    survive between turns without burning tokens in the chat log.
    """
    text = (note or "").strip()
    if not text:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "note rejected: empty",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    notes = _safe_list(state.get("agent_notes"))
    notes.append({"ts": _now(), "note": text})
    return Command(
        update={
            "agent_notes": notes,
            "messages": [
                ToolMessage(
                    f"note #{len(notes)} added ({len(text)} chars)",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def agent_note_list(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Render all stored notes in insertion order."""
    notes = _safe_list(state.get("agent_notes"))
    if not notes:
        body = "(no notes)"
    else:
        body = "\n\n".join(
            f"#{i + 1} [{n.get('ts')}]\n{n.get('note')}" for i, n in enumerate(notes)
        )
    return Command(
        update={
            "messages": [
                ToolMessage(body, tool_call_id=tool_call_id),
            ]
        }
    )


# ── finish ────────────────────────────────────────────────────────────


@tool
def agent_finish(
    summary: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Emit a final summary and clear per-agent scratch state.

    Call exactly once when the assigned objective is complete. The summary
    plus any open todos/notes are merged into a single ToolMessage so the
    orchestrator can read the result without inspecting state directly.
    Scratch fields (``agent_todo``, ``agent_notes``, ``agent_thinking``)
    are reset to empty lists.

    Note: this signals task completion at the *agent-state* layer; the graph
    itself terminates via the deepagents ``finish`` tool / orchestrator
    handoff. See :func:`decepticon.tools.interaction.complete_engagement_planning`
    for the soundwave→decepticon handoff signal.
    """
    text = (summary or "").strip() or "(no summary)"
    todos = _safe_list(state.get("agent_todo"))
    notes = _safe_list(state.get("agent_notes"))
    thinking = _safe_list(state.get("agent_thinking"))
    body_parts = [f"=== agent_finish ===\n{text}"]
    if todos:
        open_todos = [t for t in todos if t.get("status") != "done"]
        body_parts.append(
            f"\n--- todos ({len(todos)} total, {len(open_todos)} open) ---\n"
            + "\n".join(
                f"[{'x' if t.get('status') == 'done' else ' '}] #{t.get('id')} {t.get('item')}"
                for t in todos
            )
        )
    if notes:
        body_parts.append(f"\n--- notes ({len(notes)}) ---\n")
        body_parts.append("\n\n".join(n.get("note", "") for n in notes))
    if thinking:
        body_parts.append(f"\n--- thinking trail ({len(thinking)}) ---\n")
        body_parts.append("\n".join(f"- {t.get('thought', '')}" for t in thinking))
    return Command(
        update={
            "agent_todo": [],
            "agent_notes": [],
            "agent_thinking": [],
            "messages": [
                ToolMessage("\n".join(body_parts), tool_call_id=tool_call_id),
            ],
        }
    )


# ── registry ──────────────────────────────────────────────────────────

AGENT_STATE_TOOLS = [
    agent_thinking,
    agent_todo_add,
    agent_todo_complete,
    agent_todo_list,
    agent_note_add,
    agent_note_list,
    agent_finish,
]


def build_agent_state_tools() -> list:
    """Return a fresh list of agent-state tools.

    Pattern matches :func:`decepticon.tools.opplan.build_opplan_tools` —
    callers wire the returned list through ``create_agent(tools=...)`` so
    the new tools become available to the LLM alongside the rest of the
    toolkit. The middleware (:class:`AgentStateMiddleware`) is only needed
    if the caller wants the state schema extended with ``agent_todo`` /
    ``agent_notes`` / ``agent_thinking`` keys.
    """
    return list(AGENT_STATE_TOOLS)
