"""FastMCP server exposing Decepticon engagement control to external agents.

This is the seam that makes external agent runtimes (OpenClaw, Hermes, or any
MCP client) able to *drive* Decepticon: discover the available engagement
graphs, launch an authorized engagement against a target, poll its progress,
and pull findings — all over the Model Context Protocol.

The server is a thin control plane. The actual red-team work runs inside the
Decepticon LangGraph server (with its full RoE enforcement, sandbox, and
knowledge-graph persistence); this module only translates MCP tool calls into
LangGraph runs and reads the persisted findings back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from decepticon.mcp_server.config import ServerConfig, load_config
from decepticon.mcp_server.engagements import EngagementClient
from decepticon.mcp_server.findings import (
    engagement_workspace,
    load_findings_graph,
    summarize_findings,
)
from decepticon.mcp_server.models import (
    FindingsResult,
    GraphInfo,
    ScanMode,
    StartResult,
    StatusResult,
)


def _default_engagement_name() -> str:
    return "mcp-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def build_server(
    config: ServerConfig | None = None,
    *,
    client: Any | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastMCP:
    """Construct the Decepticon engagement MCP server.

    ``client`` injects a pre-built LangGraph SDK client (tests/embedding);
    production callers leave it ``None`` so it is created from ``config``.
    """
    cfg = config or load_config()
    engagements = EngagementClient(cfg, client=client)
    mcp = FastMCP("decepticon", host=host, port=port)

    @mcp.tool()
    async def decepticon_list_graphs() -> list[GraphInfo]:
        """List the engagement graphs the connected Decepticon server exposes.

        Use this first to discover which orchestrator/specialist to target
        (e.g. ``decepticon`` for a full kill-chain engagement, ``recon`` for
        reconnaissance only). Requires a running Decepticon LangGraph server.
        """
        return await engagements.list_graphs()

    @mcp.tool()
    async def decepticon_start_engagement(
        targets: list[str],
        instruction: str = "",
        scan_mode: ScanMode = "standard",
        engagement_name: str | None = None,
        assistant: str | None = None,
    ) -> StartResult:
        """Start an AUTHORIZED Decepticon engagement against one or more targets.

        ``targets`` are URLs, hostnames/CIDRs, repo URLs, or filesystem paths.
        ``instruction`` carries the scope and rules of engagement (what is in
        and out of scope) — the orchestrator's RoE enforcement gates every tool
        call against it, so be explicit. Only test assets you are authorized to
        test.

        The run is dispatched in the background and returns immediately with a
        ``thread_id``/``run_id`` handle. Poll ``decepticon_engagement_status``
        and pull ``decepticon_engagement_findings`` as results land — a full
        engagement can take many minutes.
        """
        name = engagement_name or _default_engagement_name()
        return await engagements.start(
            targets=targets,
            instruction=instruction,
            scan_mode=scan_mode,
            engagement_name=name,
            assistant=assistant or cfg.default_assistant,
        )

    @mcp.tool()
    async def decepticon_engagement_status(
        thread_id: str,
        run_id: str,
        engagement_name: str,
    ) -> StatusResult:
        """Poll a dispatched engagement: run status + whether findings exist yet.

        ``status`` is the LangGraph run status (``pending``/``running``/
        ``success``/``error``/``timeout``/``interrupted``). When
        ``findings_available`` is true, call ``decepticon_engagement_findings``.
        """
        status = await engagements.run_status(thread_id=thread_id, run_id=run_id)
        findings_available = (engagement_workspace(engagement_name) / "graph.json").exists()
        return StatusResult(
            thread_id=thread_id,
            run_id=run_id,
            status=status,
            findings_available=findings_available,
        )

    @mcp.tool()
    async def decepticon_engagement_findings(
        engagement_name: str,
        include_sarif: bool = False,
    ) -> FindingsResult:
        """Fetch the findings summary for an engagement (optionally full SARIF).

        Returns counts by SARIF level plus, when ``include_sarif`` is true, the
        complete SARIF v2.1.0 document. ``available`` is false when the
        orchestrator has not persisted findings yet.
        """
        graph = load_findings_graph(engagement_name)
        return summarize_findings(
            graph,
            engagement_name=engagement_name,
            include_sarif=include_sarif,
        )

    @mcp.tool()
    async def decepticon_cancel_engagement(thread_id: str, run_id: str) -> str:
        """Cancel a running engagement by its thread/run handle."""
        await engagements.cancel(thread_id=thread_id, run_id=run_id)
        return "cancelled"

    return mcp
