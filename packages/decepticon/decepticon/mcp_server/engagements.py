"""Drive Decepticon engagements through the LangGraph SDK.

A thin async bridge: MCP tool calls are translated into LangGraph runs
against a running Decepticon server, reusing the same scope/state payload
shape as ``decepticon.cli.scan`` so the orchestrator (and its RoE
enforcement middleware) sees an identical engagement contract whether the
trigger is the CLI or an external agent.

Engagements are dispatched as **background** runs (``runs.create``, not
``runs.stream``) so a long red-team run never blocks the calling agent's
tool call — the agent polls :meth:`EngagementClient.run_status` and pulls
findings when they appear.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from decepticon.mcp_server.config import ServerConfig
from decepticon.mcp_server.models import GraphInfo, ScanMode, StartResult
from decepticon_core.utils.logging import get_logger

log = get_logger("mcp_server.engagements")


class EngagementClient:
    """Async bridge from MCP tool calls to a running Decepticon LangGraph server.

    ``client`` is the ``langgraph_sdk`` async client. It is injectable so unit
    tests can pass a fake; in production it is created lazily from the
    configured URL.
    """

    def __init__(self, config: ServerConfig, *, client: Any | None = None) -> None:
        self._config = config
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            from langgraph_sdk import get_client

            self._client = get_client(url=self._config.langgraph_url)
        return self._client

    async def list_graphs(self) -> list[GraphInfo]:
        """Return the engagement graphs (assistants) the connected server exposes."""
        client = self._ensure_client()
        assistants = await client.assistants.search()
        return [
            GraphInfo(
                assistant_id=str(entry.get("assistant_id", "")),
                graph_id=str(entry.get("graph_id", "")),
                name=str(entry.get("name") or entry.get("graph_id") or ""),
            )
            for entry in assistants
        ]

    async def start(
        self,
        *,
        targets: Sequence[str],
        instruction: str,
        scan_mode: ScanMode,
        engagement_name: str,
        assistant: str,
    ) -> StartResult:
        """Dispatch a background engagement run and return its handle."""
        scope_payload: dict[str, Any] = {
            "targets": list(targets),
            "scope_mode": "full",
            "diff_files": [],
            "scan_mode": scan_mode,
            "instruction": instruction,
        }
        state_input: dict[str, Any] = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Run an authorized security engagement. Scope and rules "
                        "of engagement are attached as JSON:\n\n"
                        + json.dumps(scope_payload, indent=2)
                    ),
                }
            ],
            "engagement_name": engagement_name,
            "scan_scope": scope_payload,
        }
        run_config: dict[str, Any] = {
            "configurable": {"engagement_name": engagement_name, "scan_mode": scan_mode},
        }

        client = self._ensure_client()
        thread = await client.threads.create()
        thread_id = str(thread["thread_id"])
        run = await client.runs.create(
            thread_id,
            assistant_id=assistant,
            input=state_input,
            config=run_config,
        )
        log.info("dispatched engagement %s on thread %s", engagement_name, thread_id)
        return StartResult(
            engagement_name=engagement_name,
            thread_id=thread_id,
            run_id=str(run["run_id"]),
            assistant=assistant,
            status=str(run.get("status", "pending")),
            langgraph_url=self._config.langgraph_url,
        )

    async def run_status(self, *, thread_id: str, run_id: str) -> str:
        """Return the current status string of a dispatched run."""
        client = self._ensure_client()
        run = await client.runs.get(thread_id, run_id)
        return str(run.get("status", "unknown"))

    async def cancel(self, *, thread_id: str, run_id: str) -> None:
        """Cancel a running engagement."""
        client = self._ensure_client()
        await client.runs.cancel(thread_id, run_id)
