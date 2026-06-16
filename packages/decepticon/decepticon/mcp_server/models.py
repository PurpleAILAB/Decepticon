"""Typed result models for the Decepticon engagement MCP server.

These models are the structured payloads the MCP tools in
:mod:`decepticon.mcp_server.server` return to external agent runtimes
(OpenClaw, Hermes). They cross the MCP boundary, so they are Pydantic
models with JSON-friendly fields (parse-at-the-boundary).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

#: Engagement depth/timeout profile. Mirrors ``decepticon.cli.scan``'s
#: ``--scan-mode`` choices so the MCP bridge and the headless CLI agree.
ScanMode = Literal["quick", "standard", "deep"]


class GraphInfo(BaseModel):
    """A single engagement graph (assistant) exposed by the Decepticon server."""

    model_config = ConfigDict(frozen=True)

    assistant_id: str
    graph_id: str
    name: str


class StartResult(BaseModel):
    """Handle returned when a background engagement run is dispatched."""

    model_config = ConfigDict(frozen=True)

    engagement_name: str
    thread_id: str
    run_id: str
    assistant: str
    status: str
    langgraph_url: str


class RunHandle(BaseModel):
    """Handle for a turn dispatched onto an existing engagement thread."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    run_id: str
    assistant: str
    status: str


class StatusResult(BaseModel):
    """Snapshot of an engagement's latest run + whether findings exist yet."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    run_id: str | None
    status: str
    findings_available: bool


class EngagementSummary(BaseModel):
    """One row in the engagement list (for browse / resume)."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    engagement_name: str | None
    status: str
    created_at: str | None
    updated_at: str | None


class TranscriptMessage(BaseModel):
    """A single message in the orchestrator transcript."""

    model_config = ConfigDict(frozen=True)

    index: int
    role: str
    text: str
    tool_calls: list[str]
    name: str | None


class Transcript(BaseModel):
    """A window of orchestrator messages plus a cursor for incremental polling."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    run_status: str
    total: int
    next_index: int
    messages: list[TranscriptMessage]


class EngagementState(BaseModel):
    """Engagement context: OPPLAN / scope / phase + counters."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    engagement_name: str | None
    run_status: str
    message_count: int
    values: dict[str, Any]


class StreamEvent(BaseModel):
    """One event captured from a live run stream (sub-agent activity, updates)."""

    model_config = ConfigDict(frozen=True)

    event: str
    data: str


class WatchResult(BaseModel):
    """A bounded live tail of an engagement's run stream."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    run_id: str | None
    run_status: str
    events: list[StreamEvent]
    truncated: bool


class FindingsResult(BaseModel):
    """Findings summary for an engagement, optionally with the full SARIF doc."""

    model_config = ConfigDict(frozen=True)

    engagement_name: str
    available: bool
    result_count: int
    level_counts: dict[str, int]
    sarif: dict[str, Any] | None = None
