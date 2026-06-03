"""Tests for decepticon.mcp_server.engagements (LangGraph SDK bridge).

Uses an in-memory fake LangGraph client rather than a mock — the fake records
what the bridge sent so the scope/RoE payload contract is asserted directly.
"""

from __future__ import annotations

from typing import Any

from decepticon.mcp_server.config import ServerConfig
from decepticon.mcp_server.engagements import EngagementClient


class _FakeThreads:
    async def create(self) -> dict[str, Any]:
        return {"thread_id": "t-123"}


class _FakeRuns:
    def __init__(self) -> None:
        self.create_call: dict[str, Any] | None = None
        self.cancelled: tuple[str, str] | None = None

    async def create(
        self, thread_id: str, *, assistant_id: str, input: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        self.create_call = {
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "input": input,
            "config": config,
        }
        return {"run_id": "r-456", "status": "pending"}

    async def get(self, thread_id: str, run_id: str) -> dict[str, Any]:
        return {"status": "success"}

    async def cancel(self, thread_id: str, run_id: str) -> None:
        self.cancelled = (thread_id, run_id)


class _FakeAssistants:
    async def search(self) -> list[dict[str, Any]]:
        return [{"assistant_id": "a-1", "graph_id": "decepticon", "name": "decepticon"}]


class _FakeClient:
    def __init__(self) -> None:
        self.threads = _FakeThreads()
        self.runs = _FakeRuns()
        self.assistants = _FakeAssistants()


def _config() -> ServerConfig:
    return ServerConfig(
        langgraph_url="http://test:2024",
        default_assistant="decepticon",
        request_timeout_seconds=60.0,
    )


async def test_start_dispatches_background_run_with_scope() -> None:
    fake = _FakeClient()
    client = EngagementClient(_config(), client=fake)

    result = await client.start(
        targets=["https://example.com"],
        instruction="In scope: example.com. Out of scope: prod DB.",
        scan_mode="standard",
        engagement_name="eng-1",
        assistant="decepticon",
    )

    assert result.thread_id == "t-123"
    assert result.run_id == "r-456"
    assert result.status == "pending"
    assert result.engagement_name == "eng-1"
    assert result.langgraph_url == "http://test:2024"

    call = fake.runs.create_call
    assert call is not None
    assert call["assistant_id"] == "decepticon"
    assert call["config"]["configurable"]["engagement_name"] == "eng-1"
    scope = call["input"]["scan_scope"]
    assert scope["targets"] == ["https://example.com"]
    assert scope["scan_mode"] == "standard"
    assert "Out of scope" in scope["instruction"]


async def test_run_status_reads_status() -> None:
    client = EngagementClient(_config(), client=_FakeClient())
    assert await client.run_status(thread_id="t", run_id="r") == "success"


async def test_list_graphs_maps_assistants() -> None:
    client = EngagementClient(_config(), client=_FakeClient())
    graphs = await client.list_graphs()
    assert len(graphs) == 1
    assert graphs[0].graph_id == "decepticon"
    assert graphs[0].assistant_id == "a-1"


async def test_cancel_calls_sdk() -> None:
    fake = _FakeClient()
    client = EngagementClient(_config(), client=fake)
    await client.cancel(thread_id="t-9", run_id="r-9")
    assert fake.runs.cancelled == ("t-9", "r-9")
