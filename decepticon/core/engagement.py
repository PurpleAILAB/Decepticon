"""Engagement loop state and configuration models.

Defines the persistent state for the system-level engagement loop and
the configuration that controls its behavior. The loop follows the
Deep Agents ralph_mode.py pattern: system-level Python while loop
that invokes LangGraph agents with fresh context per iteration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from decepticon.core.logging import get_logger

log = get_logger("core.engagement")

# ── Enums ──────────────────────────────────────────────────────────────────────


class EngagementPhase(StrEnum):
    """Current phase of the system-level engagement loop."""

    PLANNING = "planning"
    ATTACK = "attack"
    VACCINE = "vaccine"
    COMPLETE = "complete"


class VaccineMode(StrEnum):
    """Controls when defensive vaccine actions are triggered.

    batch     — apply defenses after all attack iterations complete
    immediate — apply a defense immediately after each finding is discovered
    """

    BATCH = "batch"
    IMMEDIATE = "immediate"


# ── Config ─────────────────────────────────────────────────────────────────────


class EngagementConfig(BaseModel):
    """Configuration for the engagement loop.

    Controls target scope, iteration limits, vaccine behavior, and the
    mapping from ObjectivePhase values to LangGraph assistant IDs.
    """

    target: str = Field(description="Target specification (CIDR range, domain, etc.)")
    max_iterations: int = Field(default=50, description="Maximum attack loop iterations")
    vaccine_mode: VaccineMode = Field(
        default=VaccineMode.BATCH,
        description="When to apply defensive vaccine actions",
    )
    langgraph_url: str = Field(
        default="http://localhost:8123",
        description="LangGraph API endpoint",
    )
    agent_selection: dict[str, str] = Field(
        default_factory=lambda: {
            "recon": "recon",
            "initial-access": "exploit",
            "post-exploit": "postexploit",
            "c2": "postexploit",
            "exfiltration": "postexploit",
        },
        description="Maps ObjectivePhase values to LangGraph assistant_id names",
    )
    workspace: Path = Field(
        default=Path("/workspace"),
        description="Workspace directory for findings, state, and scratch files",
    )


# ── Iteration result ───────────────────────────────────────────────────────────


class IterationResult(BaseModel):
    """Result of one attack loop iteration."""

    objective_id: str = Field(description="ID of the objective that was executed")
    agent_used: str = Field(description="LangGraph assistant_id used for this iteration")
    outcome: str = Field(description="Signal emitted by the agent: PASSED or BLOCKED")
    findings_produced: list[str] = Field(
        default_factory=list,
        description="Finding references (e.g. FIND-001) produced during this iteration",
    )
    duration_seconds: float = Field(default=0.0, description="Wall-clock execution time")
    error: str | None = Field(default=None, description="Error message if the iteration failed")
    raw_output: str = Field(
        default="",
        description="Complete agent response text for this iteration",
    )


# ── Engagement state ───────────────────────────────────────────────────────────


class EngagementState(BaseModel):
    """Persisted state for the system-level engagement loop.

    Written to ``workspace/.engagement-state.json`` after each iteration so
    the loop can be resumed after an interruption.
    """

    phase: EngagementPhase = Field(default=EngagementPhase.PLANNING)
    iteration: int = Field(default=0, description="Current loop iteration count")
    max_iterations: int = Field(default=50, description="Maximum iterations before halting")
    current_objective_id: str | None = Field(
        default=None, description="Objective ID currently being executed"
    )
    objectives_completed: list[str] = Field(
        default_factory=list, description="Objective IDs that reached PASSED status"
    )
    objectives_blocked: list[str] = Field(
        default_factory=list, description="Objective IDs that reached BLOCKED status"
    )
    findings_discovered: list[str] = Field(
        default_factory=list, description="Finding references discovered so far"
    )
    iteration_history: list[IterationResult] = Field(
        default_factory=list, description="Per-iteration execution records"
    )
    workspace: str = Field(default="/workspace", description="Workspace directory path")
    target: str = Field(default="", description="Target specification")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the engagement loop started",
    )
    resumed_at: datetime | None = Field(
        default=None, description="UTC timestamp of the most recent resume, if any"
    )

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, workspace: Path) -> None:
        """Write state to ``workspace/.engagement-state.json``."""
        state_file = workspace / ".engagement-state.json"
        workspace.mkdir(parents=True, exist_ok=True)
        state_file.write_text(self.model_dump_json(indent=2))
        log.debug("engagement state saved to %s (iteration %d)", state_file, self.iteration)

    @classmethod
    def load(cls, workspace: Path) -> EngagementState | None:
        """Read state from ``workspace/.engagement-state.json``.

        Returns ``None`` if the file does not exist.
        """
        state_file = workspace / ".engagement-state.json"
        if not state_file.exists():
            return None
        data = state_file.read_text()
        state = cls.model_validate_json(data)
        log.debug("engagement state loaded from %s (iteration %d)", state_file, state.iteration)
        return state

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_complete(self) -> bool:
        """True when the loop should halt.

        Halts when max_iterations is reached or the phase is COMPLETE.
        """
        return self.iteration >= self.max_iterations or self.phase == EngagementPhase.COMPLETE

    @property
    def summary(self) -> dict[str, object]:
        """Counts and status overview suitable for logging or reporting."""
        total_processed = len(self.objectives_completed) + len(self.objectives_blocked)
        return {
            "phase": self.phase,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "objectives_completed": len(self.objectives_completed),
            "objectives_blocked": len(self.objectives_blocked),
            "total_processed": total_processed,
            "findings_discovered": len(self.findings_discovered),
            "is_complete": self.is_complete,
        }
