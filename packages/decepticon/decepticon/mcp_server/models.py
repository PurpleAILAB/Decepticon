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


class StatusResult(BaseModel):
    """Snapshot of a running engagement plus whether findings exist yet."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    run_id: str
    status: str
    findings_available: bool


class FindingsResult(BaseModel):
    """Findings summary for an engagement, optionally with the full SARIF doc."""

    model_config = ConfigDict(frozen=True)

    engagement_name: str
    available: bool
    result_count: int
    level_counts: dict[str, int]
    sarif: dict[str, Any] | None = None
