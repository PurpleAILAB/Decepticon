from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

CancelOutcome = Literal[
    "clean",  # run reached terminal status without harness-side cancel
    "soft_cancelled",  # cancel API call returned within deadline, run reached terminal
    "rollback",  # action="rollback" succeeded and run reached terminal
    "container_restart",  # had to restart langgraph container to dislodge wedged run
    "failed",  # cancel call failed and verify-terminal also failed
]


class Challenge(BaseModel):
    """A single benchmark challenge definition."""

    id: str = Field(description="Challenge identifier, e.g. XBEN-001-24")
    name: str
    description: str
    level: int = Field(description="Difficulty: 1=easy, 2=medium, 3=hard")
    tags: list[str]
    win_condition: str = Field(default="flag")
    compose_dir: Path = Field(description="Directory containing docker-compose.yml")

    @property
    def flag_pattern(self) -> re.Pattern[str]:
        return re.compile(r"FLAG\{[a-f0-9]+\}")


class SetupResult(BaseModel):
    """Result from setting up a challenge environment."""

    target_url: str
    container_ids: list[str] = Field(default_factory=list)
    success: bool
    error: str | None = None
    extra_ports: dict[int, int] = Field(
        default_factory=dict,
        description="Additional published ports (target_port -> host_port)",
    )


class ChallengeResult(BaseModel):
    """Result from running a single challenge."""

    challenge_id: str
    challenge_name: str
    level: int
    tags: list[str]
    passed: bool
    flag_captured: str | None = None
    duration_seconds: float = 0.0
    error: str | None = None
    # Solve evidence metadata (for public reporting)
    thread_id: str | None = None
    token_count: int | None = None
    agent_summary: str | None = None
    # Cancel/teardown introspection: ground truth for whether the LangGraph run
    # was actually halted before teardown fired. Populated by the harness
    # cancel-and-verify-terminal path; observers/critics read these to detect
    # cancel/teardown order races without scraping LangSmith.
    cancel_outcome: CancelOutcome | None = None
    terminal_status_at_teardown: str | None = None


class BenchmarkReport(BaseModel):
    """Aggregated report for a full benchmark run."""

    provider_name: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    by_level: dict[int, dict] = Field(
        description='Breakdown by level with keys "total", "passed", "pass_rate"'
    )
    by_tag: dict[str, dict] = Field(
        description='Breakdown by tag with keys "total", "passed", "pass_rate"'
    )
    results: list[ChallengeResult]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float


class FilterConfig(BaseModel):
    """Configuration for filtering which challenges to run."""

    levels: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    range_start: int | None = None
    range_end: int | None = None
