from __future__ import annotations

from pydantic import BaseModel, Field


class BenchmarkStepResult(BaseModel):
    """Single agent output captured during a benchmark run."""

    objective_id: str
    agent_used: str
    outcome: str
    findings_produced: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None
    raw_output: str = ""


class BenchmarkRunState(BaseModel):
    """Provider evaluation input assembled by the benchmark harness."""

    step_history: list[BenchmarkStepResult] = Field(default_factory=list)
