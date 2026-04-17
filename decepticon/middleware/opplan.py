"""OPPLANMiddleware — domain-specific task tracking for red team engagements.

Follows the TodoListMiddleware pattern: OPPLAN CRUD tools execute their logic
directly via InjectedState, appearing as proper `tool` type runs in LangSmith.
No middleware tool-call interception needed.

4 tools (Claude Code mapping):
  add_objective    — add single objective           (TaskCreate)
  get_objective    — read single objective detail   (TaskGet)
  list_objectives  — list all + progress summary    (TaskList)
  update_objective — update status/notes/owner      (TaskUpdate)

Key differences from Claude Code:
  - Domain: Task → Objective, project → engagement, coding → kill chain
  - Enum-typed parameters (ObjectivePhase, OpsecLevel, C2Tier)
  - Kill chain dependencies (blocked_by) with execution-time validation
  - Dynamic OPPLAN status injection every LLM call (battle tracker)
  - Parallel mutation prevention (sequential counter-based IDs)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, NotRequired, cast, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import OmitFromInput
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from decepticon.core.schemas import (
    OPPLAN,
    C2Tier,
    Objective,
    ObjectivePhase,
    ObjectiveStatus,
    OpsecLevel,
)

# ── State Schema ──────────────────────────────────────────────────────


class OPPLANState(AgentState):
    """Extended agent state with OPPLAN objectives.

    Merged automatically by create_agent() when OPPLANMiddleware
    is in the middleware stack. All fields are excluded from input schema
    (OmitFromInput) — only the middleware tools can write to them.
    """

    objectives: Annotated[NotRequired[list[dict]], OmitFromInput]
    """List of OPPLAN objectives in dict form (serialized Objective models)."""

    engagement_name: Annotated[NotRequired[str], OmitFromInput]
    """Current engagement name for context."""

    threat_profile: Annotated[NotRequired[str], OmitFromInput]
    """Threat actor profile for context injection."""

    objective_counter: Annotated[NotRequired[int], OmitFromInput]
    """Auto-increment counter for objective IDs (like Claude Code high water mark)."""

    workspace_path: Annotated[NotRequired[str], OmitFromInput]
    """Engagement workspace root path — set by save_opplan/load_opplan."""


# ── System Prompt ─────────────────────────────────────────────────────

OPPLAN_SYSTEM_PROMPT = """\
## OPPLAN — Operational Plan Tracking

You have OPPLAN tools to manage red team engagement objectives.
These are always available — no mode switching needed.

### Objective CRUD Tools

- **`add_objective`** — Add a single objective (auto-ID: OBJ-001, OBJ-002, ...).
  Each objective MUST be completable in ONE sub-agent context window.
  Set `engagement_name` and `threat_profile` on the first call to initialize context.

- **`get_objective`** — Read a single objective's full details.
  ALWAYS call this before update_objective (read-before-write, staleness prevention).

- **`list_objectives`** — List all objectives with progress summary.
  Use when: Selecting the next objective, reviewing progress, situational awareness.

- **`update_objective`** — Update status, notes, or owner.
  ALWAYS call get_objective first. NEVER call multiple times in parallel.

- **`objective_expand`** — Break a parent objective into N child sub-tasks.
  Use when an objective is broad or when discovered work reveals sub-tasks —
  keep each leaf small enough to complete in one sub-agent iteration.
  This is the Pentesting Task Tree (PTT) pattern. Parents cannot move to
  COMPLETED until every child is COMPLETED or CANCELLED.

- **`objective_collapse`** — Cancel every descendant of a parent objective.
  Use when abandoning a hierarchical task so the parent can then be moved
  to COMPLETED or CANCELLED itself.

- **`save_opplan`** — Persist the current OPPLAN state to `plan/opplan.json`.
  Call after the user approves the plan and after any major re-planning.
  Validates all objectives against the Pydantic schema before writing.

- **`load_opplan`** — Hydrate agent state from an existing `plan/opplan.json`.
  Call on session startup if the engagement already has an OPPLAN file.

### Workflow
```
add_objective(×N, engagement_name=...) → [user approval] → save_opplan → Ralph Loop
          ↓
objective_expand(parent_id, children=[...])   # split broad work on demand
```

### Status Transitions
```
pending → in-progress → completed    (evidence documented)
                       → blocked      (failure reason documented)
                       → cancelled    (abandon cleanly)
blocked → in-progress                 (retry with different approach)
        → completed                   (abandon with explanation)
        → cancelled                   (drop from plan)
```

### Rules — NEVER Violate
- NEVER execute objectives without user-approved OPPLAN
- NEVER call update_objective without calling get_objective first
- NEVER call update_objective multiple times in parallel
- ALWAYS include evidence when marking COMPLETED
- ALWAYS include failure reason and attempts when marking BLOCKED
- ALWAYS set owner to the sub-agent name before delegating (recon/exploit/postexploit)
- ALWAYS respect blocked_by dependencies and kill chain phase order
"""


# ── State Transition Rules ────────────────────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in-progress", "cancelled"},
    "in-progress": {"completed", "blocked", "cancelled"},
    "blocked": {"in-progress", "completed", "cancelled"},  # retry, abandon, drop
    # completed is terminal
    # cancelled is terminal
}


# ── Formatting Helpers ────────────────────────────────────────────────


#: Maximum number of objective rows ``_format_opplan_status`` will
#: render into the system prompt. Past this cap, completed/cancelled
#: objectives collapse into a single summary line and only the
#: actionable (pending / in-progress / blocked) ones retain a full
#: table row. Overridable via ``DECEPTICON_OPPLAN_MAX_ROWS``.
try:
    _OPPLAN_MAX_ROWS = int(os.environ.get("DECEPTICON_OPPLAN_MAX_ROWS", "40"))
except ValueError:
    _OPPLAN_MAX_ROWS = 40

_STATUS_MARKERS = {
    "completed": "COMPLETED",
    "blocked": "BLOCKED",
    "cancelled": "CANCELLED",
    "in-progress": ">>IN-PROGRESS<<",
    "pending": "pending",
}

_TERMINAL_STATUSES = {"completed", "cancelled"}


def _format_opplan_status(
    objectives: list[dict],
    engagement_name: str,
    threat_profile: str,
) -> str:
    """Format OPPLAN for system prompt injection (concise battle tracker).

    Injected every LLM call via wrap_model_call, providing dynamic
    situational awareness — the red team equivalent of a battle
    tracker. To bound token cost on long / deeply-expanded plans we
    trim terminal objectives (completed / cancelled) from the main
    table once the total row count exceeds ``_OPPLAN_MAX_ROWS``.
    """
    total = len(objectives)
    completed = 0
    blocked = 0
    in_progress = 0
    pending = 0
    cancelled = 0
    for o in objectives:
        status = o.get("status") or ""
        if status == "completed":
            completed += 1
        elif status == "blocked":
            blocked += 1
        elif status == "in-progress":
            in_progress += 1
        elif status == "pending":
            pending += 1
        elif status == "cancelled":
            cancelled += 1

    actionable = [o for o in objectives if o.get("status") in ("pending", "in-progress")]
    actionable.sort(key=lambda o: o.get("priority", 999))
    next_obj = actionable[0] if actionable else None

    progress_line = (
        f"Progress: {completed}/{total} completed, {blocked} blocked, "
        f"{in_progress} in-progress, {pending} pending"
    )
    if cancelled:
        progress_line += f", {cancelled} cancelled"

    lines = [
        "<OPPLAN_STATUS>",
        f"Engagement: {engagement_name}",
        f"Threat Profile: {threat_profile}",
        progress_line,
        "",
        "| ID | Phase | Title | Status | Priority | Owner |",
        "|---|---|---|---|---|---|",
    ]

    # Render actionable objectives in full, then terminal ones only
    # until the row budget is exhausted.
    sorted_objectives = sorted(objectives, key=lambda x: x.get("priority", 999))
    actionable_rows: list[dict[str, Any]] = []
    terminal_rows: list[dict[str, Any]] = []
    for o in sorted_objectives:
        if o.get("status") in _TERMINAL_STATUSES:
            terminal_rows.append(o)
        else:
            actionable_rows.append(o)

    rendered = 0
    for o in actionable_rows:
        status_marker = _STATUS_MARKERS.get(o.get("status", ""), o.get("status", ""))
        lines.append(
            f"| {o.get('id', '?')} | {o.get('phase', '?')} | "
            f"{o.get('title', '?')} | {status_marker} | "
            f"{o.get('priority', '?')} | {o.get('owner') or '-'} |"
        )
        rendered += 1

    remaining_budget = max(0, _OPPLAN_MAX_ROWS - rendered)
    shown_terminal = terminal_rows[:remaining_budget]
    for o in shown_terminal:
        status_marker = _STATUS_MARKERS.get(o.get("status", ""), o.get("status", ""))
        lines.append(
            f"| {o.get('id', '?')} | {o.get('phase', '?')} | "
            f"{o.get('title', '?')} | {status_marker} | "
            f"{o.get('priority', '?')} | {o.get('owner') or '-'} |"
        )
    hidden = len(terminal_rows) - len(shown_terminal)
    if hidden > 0:
        lines.append(f"| … | … | _{hidden} more terminal objectives_ | … | … | … |")

    if next_obj:
        lines.extend(
            [
                "",
                f"**Next**: {next_obj.get('id')} — {next_obj.get('title')}",
                f"  Phase: {next_obj.get('phase')} | "
                f"MITRE: {', '.join(next_obj.get('mitre') or []) or 'n/a'} | "
                f"OPSEC: {next_obj.get('opsec', 'standard')} | "
                f"C2: {next_obj.get('c2_tier', 'interactive')}",
            ]
        )
        criteria = next_obj.get("acceptance_criteria", [])
        if criteria:
            lines.append("  Acceptance Criteria:")
            for c in criteria:
                lines.append(f"    - [ ] {c}")
    else:
        lines.append("")
        all_done = all(o.get("status") == "completed" for o in objectives)
        if all_done:
            lines.append("**ALL OBJECTIVES COMPLETE** — Generate final engagement report.")
        else:
            lines.append("**No actionable objectives** — Review blocked items for retry.")

    lines.append("</OPPLAN_STATUS>")
    return "\n".join(lines)


def _format_opplan_for_agent(
    objectives: list[dict],
    engagement_name: str,
    threat_profile: str,
) -> str:
    """Format OPPLAN for list_objectives response (detailed overview).

    When any objective has ``parent_id`` set, the output includes an
    indented tree view after the flat table so the agent can see the
    hierarchy at a glance.
    """
    total = len(objectives)
    completed = sum(1 for o in objectives if o.get("status") == "completed")
    blocked = sum(1 for o in objectives if o.get("status") == "blocked")

    has_tree = any(o.get("parent_id") for o in objectives)

    lines = [
        f"# OPPLAN: {engagement_name}",
        f"Threat Profile: {threat_profile}",
        f"Progress: {completed}/{total} completed, {blocked} blocked",
        "",
        "| ID | Phase | Title | Status | Priority | Owner | Blocked By |",
        "|---|---|---|---|---|---|---|",
    ]

    for o in sorted(objectives, key=lambda x: x.get("priority", 999)):
        status = o.get("status", "pending")
        blocked_by = ", ".join(o.get("blocked_by", [])) or "-"
        title = o.get("title", "?")
        if o.get("parent_id"):
            title = f"↳ {title}"
        lines.append(
            f"| {o.get('id', '?')} | {o.get('phase', '?')} | "
            f"{title} | {status} | "
            f"{o.get('priority', '?')} | {o.get('owner') or '-'} | "
            f"{blocked_by} |"
        )

    lines.append("")

    if has_tree:
        lines.append("## Task Tree")

        def _render(parent_id: str | None, depth: int) -> None:
            kids = sorted(
                [o for o in objectives if o.get("parent_id") == parent_id],
                key=lambda x: x.get("priority", 999),
            )
            for o in kids:
                indent = "  " * depth
                status = o.get("status", "pending")
                marker = {
                    "completed": "[x]",
                    "blocked": "[!]",
                    "cancelled": "[-]",
                    "in-progress": "[~]",
                }.get(status, "[ ]")
                lines.append(
                    f"{indent}- {marker} {o.get('id', '?')} {o.get('title', '?')} ({status})"
                )
                _render(o["id"], depth + 1)

        _render(None, 0)
        lines.append("")

    # Next objective recommendation
    actionable = [o for o in objectives if o.get("status") in ("pending", "in-progress")]
    actionable.sort(key=lambda o: o.get("priority", 999))
    if actionable:
        nxt = actionable[0]
        lines.append(
            f"Next: {nxt.get('id')} — {nxt.get('title')} "
            f"(phase: {nxt.get('phase')}, priority: {nxt.get('priority')})"
        )
    else:
        all_done = all(o.get("status") == "completed" for o in objectives)
        if all_done:
            lines.append("ALL OBJECTIVES COMPLETE — Generate final engagement report.")
        else:
            lines.append("No actionable objectives — review blocked items for retry.")

    return "\n".join(lines)


# ── Tool Definitions ──────────────────────────────────────────────────


def _make_tools() -> list:
    """Create OPPLAN tools with InjectedState for direct state access.

    Follows TodoListMiddleware pattern: tool bodies execute CRUD logic directly,
    returning Command for state mutations. No middleware interception needed —
    tools appear as proper `tool` type runs in LangSmith.
    """

    @tool(
        description=(
            "Add a single objective to the OPPLAN. Auto-generates an ID "
            "(OBJ-001, OBJ-002, ...). Each objective must be completable in "
            "ONE sub-agent context window. Use blocked_by to set kill chain dependencies. "
            "Set engagement_name and threat_profile on the first call to initialize context."
        )
    )
    def add_objective(
        title: str,
        phase: ObjectivePhase,
        description: str,
        acceptance_criteria: list[str],
        priority: int,
        state: Annotated[dict, InjectedState],
        engagement_name: str | None = None,
        threat_profile: str | None = None,
        mitre: list[str] | None = None,
        opsec: OpsecLevel = OpsecLevel.STANDARD,
        opsec_notes: str = "",
        c2_tier: C2Tier = C2Tier.INTERACTIVE,
        concessions: list[str] | None = None,
        blocked_by: list[str] | None = None,
        parent_id: str | None = None,
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Add one objective with auto-ID generation."""
        counter = state.get("objective_counter", 0) + 1
        obj_id = f"OBJ-{counter:03d}"

        # Validate parent_id if supplied
        if parent_id:
            existing_ids = {o.get("id") for o in state.get("objectives", [])}
            if parent_id not in existing_ids:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=(
                                    f"Parent objective '{parent_id}' not found. "
                                    f"Existing: {', '.join(sorted(i for i in existing_ids if i))}"
                                ),
                                tool_call_id=tool_call_id,
                                status="error",
                            )
                        ],
                    }
                )

        obj_dict = {
            "id": obj_id,
            "title": title,
            "phase": phase,
            "description": description,
            "acceptance_criteria": acceptance_criteria,
            "priority": priority,
            "status": "pending",
            "mitre": mitre or [],
            "opsec": opsec,
            "opsec_notes": opsec_notes,
            "c2_tier": c2_tier,
            "concessions": concessions or [],
            "blocked_by": blocked_by or [],
            "owner": "",
            "notes": "",
            "parent_id": parent_id,
        }

        # Pydantic validation
        try:
            Objective(**obj_dict)
        except Exception as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Validation failed for objective: {e}",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )

        objectives = list(state.get("objectives", []))
        objectives.append(obj_dict)

        # Build state update — always include objectives + counter
        update: dict[str, Any] = {
            "objectives": objectives,
            "objective_counter": counter,
            "messages": [
                ToolMessage(
                    content=(
                        f"Added {obj_id}: {obj_dict['title']} "
                        f"(phase: {obj_dict['phase']}, priority: {obj_dict['priority']})"
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }

        # Set engagement metadata if provided (typically on first call)
        if engagement_name:
            update["engagement_name"] = engagement_name
        if threat_profile:
            update["threat_profile"] = threat_profile

        return Command(update=update)

    @tool(
        description=(
            "Read a single objective's full details by ID. "
            "ALWAYS call this before update_objective to prevent staleness. "
            "Returns: status, description, acceptance criteria, dependencies, notes."
        )
    )
    def get_objective(
        objective_id: str,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Read one objective detail from state."""
        objectives = state.get("objectives", [])
        target = next((o for o in objectives if o.get("id") == objective_id), None)

        if not target:
            available = ", ".join(o.get("id", "?") for o in objectives)
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                f"Objective '{objective_id}' not found. "
                                f"Available: {available or 'none (use add_objective first)'}"
                            ),
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )

        obj_status = target.get("status", "pending")
        mitre_ids = target.get("mitre") or []
        mitre_str = ", ".join(mitre_ids) if mitre_ids else "n/a"
        lines = [
            f"## {target['id']} [{obj_status.upper()}]",
            f"Title: {target.get('title', '')}",
            f"Phase: {target.get('phase', '')} | Priority: {target.get('priority', '')}",
            f"MITRE: {mitre_str}",
            f"OPSEC: {target.get('opsec', 'standard')} | C2: {target.get('c2_tier', 'interactive')}",
            f"Description: {target.get('description', '')}",
        ]

        criteria = target.get("acceptance_criteria", [])
        if criteria:
            check = "x" if obj_status == "completed" else " "
            lines.append("Acceptance Criteria:")
            for c in criteria:
                lines.append(f"  - [{check}] {c}")

        blocked_by_ids = target.get("blocked_by", [])
        if blocked_by_ids:
            lines.append(f"Blocked By: {', '.join(blocked_by_ids)}")

        owner = target.get("owner", "")
        if owner:
            lines.append(f"Owner: {owner}")

        obj_opsec_notes = target.get("opsec_notes", "")
        if obj_opsec_notes:
            lines.append(f"OPSEC Notes: {obj_opsec_notes}")

        obj_concessions = target.get("concessions") or []
        if obj_concessions:
            lines.append("Concessions:")
            for c in obj_concessions:
                lines.append(f"  - {c}")

        notes = target.get("notes", "")
        if notes:
            lines.append(f"Notes: {notes}")

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="\n".join(lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool(
        description=(
            "List all OPPLAN objectives with progress summary. "
            "Returns: engagement overview, objective table with status, "
            "and next recommended objective."
        )
    )
    def list_objectives(
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """List all objectives with progress summary."""
        objectives = state.get("objectives", [])
        engagement = state.get("engagement_name", "")
        threat = state.get("threat_profile", "")

        if not objectives:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content="No objectives defined yet. Use `add_objective` to create objectives.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        content = _format_opplan_for_agent(objectives, engagement, threat)
        return Command(
            update={
                "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)],
            }
        )

    @tool(
        description=(
            "Update a single objective. MUST call get_objective first. "
            "Can change: status, notes, owner, add_blocked_by. "
            "Valid transitions: pending→in-progress, in-progress→completed/blocked, "
            "blocked→in-progress (retry) or completed (abandon). "
            "Include evidence when marking completed, failure reason when marking blocked."
        )
    )
    def update_objective(
        objective_id: str,
        state: Annotated[dict, InjectedState],
        status: str | None = None,
        notes: str | None = None,
        owner: str | None = None,
        add_blocked_by: list[str] | None = None,
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Update one objective with state transition validation."""
        # Deep copy objectives to avoid mutating state
        objectives = [dict(o) for o in state.get("objectives", [])]
        target = next((o for o in objectives if o.get("id") == objective_id), None)

        if not target:
            available = ", ".join(o.get("id", "?") for o in objectives)
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Objective '{objective_id}' not found. Available: {available}",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )

        updated_fields: list[str] = []

        # ── Status change with transition + dependency validation ─────
        if status is not None:
            # Validate status value
            try:
                ObjectiveStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in ObjectiveStatus)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=f"Invalid status '{status}'. Valid: {valid}",
                                tool_call_id=tool_call_id,
                                status="error",
                            )
                        ],
                    }
                )

            current = target.get("status", "pending")
            if not _is_valid_transition(current, status):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=(
                                    f"Invalid transition: {current} → {status}. "
                                    f"Valid from '{current}': {_valid_next(current)}"
                                ),
                                tool_call_id=tool_call_id,
                                status="error",
                            )
                        ],
                    }
                )

            # Check blocked_by dependencies when starting execution
            if status == "in-progress":
                blocked_by_ids = target.get("blocked_by", [])
                unresolved = [
                    bid
                    for bid in blocked_by_ids
                    if any(
                        o.get("id") == bid and o.get("status") != "completed" for o in objectives
                    )
                ]
                if unresolved:
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    content=(
                                        f"Cannot start {objective_id}: "
                                        f"blocked by unresolved objectives: {', '.join(unresolved)}"
                                    ),
                                    tool_call_id=tool_call_id,
                                    status="error",
                                )
                            ],
                        }
                    )

            # Parents cannot complete until every child is done.
            if status == "completed":
                children = [o for o in objectives if o.get("parent_id") == objective_id]
                if children:
                    unresolved_kids = [
                        c["id"]
                        for c in children
                        if c.get("status") not in {"completed", "cancelled"}
                    ]
                    if unresolved_kids:
                        return Command(
                            update={
                                "messages": [
                                    ToolMessage(
                                        content=(
                                            f"Cannot complete {objective_id}: "
                                            f"children still open: {', '.join(unresolved_kids)}. "
                                            f"Complete or cancel each child first, or call "
                                            f"objective_collapse({objective_id})."
                                        ),
                                        tool_call_id=tool_call_id,
                                        status="error",
                                    )
                                ],
                            }
                        )

            target["status"] = status
            updated_fields.append(f"status → {status}")

        # ── Notes ─────────────────────────────────────────────────────
        if notes is not None:
            target["notes"] = notes
            updated_fields.append("notes")

        # ── Owner (which sub-agent is executing) ─────────────────────
        if owner is not None:
            target["owner"] = owner
            updated_fields.append("owner")

        # ── Add blocked_by dependencies ──────────────────────────────
        if add_blocked_by:
            existing_blocked = set(target.get("blocked_by", []))
            all_ids = {o.get("id") for o in objectives}
            invalid = [bid for bid in add_blocked_by if bid not in all_ids]
            if invalid:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=f"Invalid blocked_by references: {', '.join(invalid)}",
                                tool_call_id=tool_call_id,
                                status="error",
                            )
                        ],
                    }
                )
            for bid in add_blocked_by:
                existing_blocked.add(bid)
            target["blocked_by"] = sorted(existing_blocked)
            updated_fields.append("blocked_by")

        if not updated_fields:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"No changes specified for {objective_id}.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        total = len(objectives)
        completed_count = sum(1 for o in objectives if o.get("status") == "completed")

        return Command(
            update={
                "objectives": objectives,
                "messages": [
                    ToolMessage(
                        content=(
                            f"Updated {objective_id}: {', '.join(updated_fields)}. "
                            f"Progress: {completed_count}/{total} completed."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool(
        description=(
            "Expand a parent objective into one or more child sub-tasks. "
            "Each child inherits the parent's phase by default but can override it. "
            "Children auto-receive IDs (OBJ-NNN) and are added with status 'pending'. "
            "The parent cannot move to COMPLETED until every child is COMPLETED or CANCELLED. "
            "Use this when an objective is broad or when recon reveals sub-tasks — it is "
            "the Pentesting Task Tree (PTT) pattern. Keep children small enough to complete "
            "in one sub-agent iteration."
        )
    )
    def objective_expand(
        parent_id: str,
        children: list[dict],
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Create ``len(children)`` child objectives under ``parent_id``.

        Each child dict must have: ``title`` (str), ``description`` (str),
        ``acceptance_criteria`` (list[str]). Optional: ``phase``
        (ObjectivePhase value, default inherited from parent),
        ``priority`` (int, default parent.priority + N), ``mitre``,
        ``blocked_by``.
        """
        objectives = [dict(o) for o in state.get("objectives", [])]
        parent = next((o for o in objectives if o.get("id") == parent_id), None)
        if parent is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Parent objective '{parent_id}' not found.",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )
        if parent.get("status") in {"completed", "cancelled"}:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                f"Cannot expand {parent_id}: status is "
                                f"{parent.get('status')}. Expand open parents only."
                            ),
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )
        if not children:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content="children list is empty — nothing to expand.",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )

        counter = state.get("objective_counter", 0)
        created_ids: list[str] = []
        parent_phase = parent.get("phase")
        parent_priority = int(parent.get("priority", 100))
        for idx, child in enumerate(children, start=1):
            counter += 1
            obj_id = f"OBJ-{counter:03d}"
            title = str(child.get("title", "")).strip()
            description = str(child.get("description", "")).strip()
            acceptance = child.get("acceptance_criteria") or []
            if not title or not description or not acceptance:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=(
                                    f"Child #{idx} missing required fields "
                                    "(title, description, acceptance_criteria)."
                                ),
                                tool_call_id=tool_call_id,
                                status="error",
                            )
                        ],
                    }
                )
            phase = child.get("phase", parent_phase)
            priority = int(child.get("priority", parent_priority + idx))
            child_dict = {
                "id": obj_id,
                "title": title,
                "phase": phase,
                "description": description,
                "acceptance_criteria": list(acceptance),
                "priority": priority,
                "status": "pending",
                "mitre": list(child.get("mitre") or []),
                "opsec": parent.get("opsec", "standard"),
                "opsec_notes": "",
                "c2_tier": parent.get("c2_tier", "interactive"),
                "concessions": [],
                "blocked_by": list(child.get("blocked_by") or []),
                "owner": "",
                "notes": "",
                "parent_id": parent_id,
            }
            try:
                Objective(**child_dict)
            except Exception as e:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=f"Child #{idx} validation failed: {e}",
                                tool_call_id=tool_call_id,
                                status="error",
                            )
                        ],
                    }
                )
            objectives.append(child_dict)
            created_ids.append(obj_id)

        return Command(
            update={
                "objectives": objectives,
                "objective_counter": counter,
                "messages": [
                    ToolMessage(
                        content=(
                            f"Expanded {parent_id} into {len(created_ids)} children: "
                            f"{', '.join(created_ids)}"
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool(
        description=(
            "Cancel every descendant of a parent objective. Use when abandoning a "
            "hierarchical task — sets each child's status to 'cancelled' so the "
            "parent can then be moved to COMPLETED or CANCELLED itself. "
            "Only pending / in-progress / blocked children are touched; already-done "
            "children are left as-is."
        )
    )
    def objective_collapse(
        parent_id: str,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Mark every descendant of ``parent_id`` as cancelled."""
        objectives = [dict(o) for o in state.get("objectives", [])]
        if not any(o.get("id") == parent_id for o in objectives):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Parent objective '{parent_id}' not found.",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )

        # Walk descendants depth-first
        stack = [parent_id]
        descendants: list[dict[str, Any]] = []
        while stack:
            current = stack.pop()
            for o in objectives:
                if o.get("parent_id") == current:
                    descendants.append(o)
                    stack.append(o["id"])

        cancelled: list[str] = []
        for o in descendants:
            if o.get("status") in {"pending", "in-progress", "blocked"}:
                o["status"] = "cancelled"
                cancelled.append(o["id"])

        return Command(
            update={
                "objectives": objectives,
                "messages": [
                    ToolMessage(
                        content=(
                            f"Cancelled {len(cancelled)} descendants of {parent_id}"
                            + (f": {', '.join(cancelled)}" if cancelled else "")
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool(
        description=(
            "Persist the current OPPLAN to plan/opplan.json in the engagement workspace. "
            "Validates all objectives against the Pydantic schema before writing. "
            "Call after the user approves the plan and after any major re-planning. "
            "Sets workspace_path in state for subsequent calls."
        )
    )
    def save_opplan(
        workspace_path: str,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Serialize state objectives → OPPLAN schema → plan/opplan.json."""
        objectives_raw = state.get("objectives", [])
        engagement_name = state.get("engagement_name", "")
        threat_profile = state.get("threat_profile", "")

        try:
            objectives = [Objective(**o) for o in objectives_raw]
        except Exception as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"OPPLAN validation failed: {e}",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ]
                }
            )

        opplan = OPPLAN(
            engagement_name=engagement_name,
            threat_profile=threat_profile,
            objectives=objectives,
        )

        plan_dir = Path(workspace_path) / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        out_path = plan_dir / "opplan.json"
        out_path.write_text(
            json.dumps(opplan.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return Command(
            update={
                "workspace_path": workspace_path,
                "messages": [
                    ToolMessage(
                        content=(
                            f"OPPLAN saved to {out_path} "
                            f"({len(objectives)} objectives, engagement: {engagement_name})"
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool(
        description=(
            "Load an existing plan/opplan.json into agent state to resume an engagement. "
            "Call on session startup when plan/opplan.json already exists — "
            "this hydrates objectives, engagement_name, and threat_profile into state "
            "so OPPLAN tools and the status tracker work immediately."
        )
    )
    def load_opplan(
        workspace_path: str,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command[Any]:
        """Read plan/opplan.json and hydrate agent state."""
        path = Path(workspace_path) / "plan" / "opplan.json"
        if not path.exists():
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                f"No opplan.json found at {path}. "
                                "Use add_objective to create a new OPPLAN."
                            ),
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ]
                }
            )

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            opplan = OPPLAN(**data)
        except Exception as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Failed to load opplan.json: {e}",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ]
                }
            )

        objectives_raw = [o.model_dump() for o in opplan.objectives]

        # Derive counter from highest existing ID so new objectives don't collide
        counter = 0
        for o in opplan.objectives:
            try:
                n = int(o.id.replace("OBJ-", ""))
                if n > counter:
                    counter = n
            except (ValueError, AttributeError):
                pass

        return Command(
            update={
                "objectives": objectives_raw,
                "engagement_name": opplan.engagement_name,
                "threat_profile": opplan.threat_profile,
                "objective_counter": counter,
                "workspace_path": workspace_path,
                "messages": [
                    ToolMessage(
                        content=(
                            f"Loaded {len(objectives_raw)} objectives from {path}. "
                            f"Engagement: {opplan.engagement_name} | "
                            f"Counter at OBJ-{counter:03d}"
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    return [
        add_objective,
        get_objective,
        list_objectives,
        update_objective,
        objective_expand,
        objective_collapse,
        save_opplan,
        load_opplan,
    ]


# ── Middleware Class ──────────────────────────────────────────────────


class OPPLANMiddleware(AgentMiddleware):
    """Domain-specific OPPLAN tracking for red team engagements.

    Follows TodoListMiddleware pattern: tools execute CRUD logic directly
    via InjectedState, appearing as proper `tool` type runs in LangSmith.

    - __init__: creates 4 CRUD tools
    - wrap_model_call: injects dynamic OPPLAN progress into system message
    - after_model: validates no parallel state-mutating calls

    State schema (OPPLANState) is auto-merged by create_agent().
    """

    state_schema = OPPLANState

    def __init__(self) -> None:
        super().__init__()
        self.tools = _make_tools()

    # ── wrap_model_call: inject OPPLAN context ────────────────────────

    @override
    def wrap_model_call(self, request, handler):
        """Inject OPPLAN system prompt + dynamic progress into system message."""
        return handler(self._inject_opplan_context(request))

    @override
    async def awrap_model_call(self, request, handler):
        """Async variant — identical logic."""
        return await handler(self._inject_opplan_context(request))

    def _inject_opplan_context(self, request):
        """Build request with OPPLAN context injected into system message.

        Injects dynamic state — the red team equivalent of a battle tracker —
        every call, providing real-time situational awareness to the LLM.
        """
        objectives = request.state.get("objectives", [])
        engagement = request.state.get("engagement_name", "")
        threat = request.state.get("threat_profile", "")

        dynamic_parts = [OPPLAN_SYSTEM_PROMPT]

        if objectives:
            dynamic_parts.append(_format_opplan_status(objectives, engagement, threat))

        injection = "\n\n".join(dynamic_parts)

        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": f"\n\n{injection}"},
            ]
        else:
            new_content = [{"type": "text", "text": injection}]

        new_system = SystemMessage(content=cast("list[str | dict[str, str]]", new_content))
        return request.override(system_message=new_system)

    # ── after_model: validate constraints ─────────────────────────────

    @override
    def after_model(self, state, runtime):
        """Validate: no parallel state-mutating OPPLAN calls.

        add_objective and update_objective both write to the objectives list.
        Parallel calls read the same stale state, causing concurrent update
        errors. Force sequential execution like Claude Code's Task tools.
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)),
            None,
        )
        if not last_ai or not last_ai.tool_calls:
            return None

        # Block parallel state-mutating calls (add + update both write objectives)
        mutating_calls = [
            tc for tc in last_ai.tool_calls if tc["name"] in ("add_objective", "update_objective")
        ]
        if len(mutating_calls) > 1:
            return {
                "messages": [
                    ToolMessage(
                        content=(
                            "Error: OPPLAN state-mutating tools (add_objective, update_objective) "
                            "must be called one at a time, not in parallel. Each call needs "
                            "the updated objectives list. Call one, wait for the result, "
                            "then call the next."
                        ),
                        tool_call_id=tc["id"],
                        status="error",
                    )
                    for tc in mutating_calls
                ]
            }

        return None

    @override
    async def aafter_model(self, state, runtime):
        """Async variant delegates to sync."""
        return self.after_model(state, runtime)


# ── Module-level helpers ──────────────────────────────────────────────


def _is_valid_transition(current: str, new: str) -> bool:
    """Check if a status transition is allowed."""
    return new in _VALID_TRANSITIONS.get(current, set())


def _valid_next(current: str) -> str:
    """Return comma-separated valid next statuses."""
    return ", ".join(sorted(_VALID_TRANSITIONS.get(current, set())))
