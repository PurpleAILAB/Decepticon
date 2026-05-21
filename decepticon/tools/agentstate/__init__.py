"""Per-agent state tools — Strix-style scratch primitives.

Mirrors Strix's ``thinking``, ``todo``, ``notes``, ``finish`` agent-local
state tools. Distinct from :mod:`decepticon.tools.opplan`, which tracks
engagement-wide objectives across the whole graph.

These tools are agent-local scratch state:
  * ``agent_thinking``  — record a structured chain-of-thought entry.
  * ``agent_todo_add`` / ``agent_todo_complete`` / ``agent_todo_list``
    — manage a per-agent todo list.
  * ``agent_note_add`` / ``agent_note_list`` — free-form memo store.
  * ``agent_finish`` — emit completion summary + signal end-of-objective.

State is held inside the LangGraph ``AgentState`` via injected tool args,
so each agent's scratch is isolated from siblings. Persistence beyond the
graph run is the agent author's responsibility (use ``write_file`` if a
follow-up agent needs to read it).
"""

from decepticon.tools.agentstate.tools import AGENT_STATE_TOOLS, build_agent_state_tools

__all__ = ["AGENT_STATE_TOOLS", "build_agent_state_tools"]
