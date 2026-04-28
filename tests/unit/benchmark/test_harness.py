"""Tests for benchmark.harness.Harness.

Marked ``slow`` because several tests exercise the harness's wall-clock
timeout / workspace teardown behavior and individually take ~120s. The
PR fast lane (``-m "not slow"``) skips them for quick feedback; the
main coverage lane runs the full set so coverage stays honest.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from benchmark.config import BenchmarkConfig
from benchmark.harness import AgentResponse, Harness
from benchmark.schemas import Challenge, SetupResult

pytestmark = pytest.mark.slow


def _make_challenge(tmp_path: Path) -> Challenge:
    return Challenge(
        id="XBEN-001-24",
        name="Test Challenge",
        description="Test",
        level=1,
        tags=["xss"],
        compose_dir=tmp_path,
    )


def _make_provider() -> MagicMock:
    provider = MagicMock()
    provider.name = "test"
    provider.setup.return_value = SetupResult(
        target_url="http://localhost:8080",
        success=True,
    )
    provider.teardown.return_value = None
    return provider


class TestHarness:
    @pytest.mark.asyncio
    async def test_workspace_creation(self, tmp_path: Path) -> None:
        """Verify harness creates workspace directory at correct path."""
        provider = _make_provider()
        provider.evaluate.return_value = MagicMock(
            challenge_id="XBEN-001-24",
            challenge_name="Test",
            level=1,
            tags=["xss"],
            passed=True,
            duration_seconds=0.0,
        )

        config = BenchmarkConfig(cleanup_workspaces=False)
        harness = Harness(provider=provider, config=config)
        harness._invoke_agent = AsyncMock(
            return_value=AgentResponse(text="No flag found", thread_id="test-thread")
        )
        challenge = _make_challenge(tmp_path)

        workspace_path = (Path.home() / f".decepticon/workspace/benchmark-{challenge.id}").resolve()

        await harness.run_challenge(challenge)

        assert workspace_path.exists()

        # Clean up manually since cleanup_workspaces=False
        import shutil

        if workspace_path.exists():
            shutil.rmtree(workspace_path)

    @pytest.mark.asyncio
    async def test_workspace_cleanup(self, tmp_path: Path) -> None:
        """Verify workspace is removed after run when cleanup_workspaces=True."""
        provider = _make_provider()
        provider.evaluate.return_value = MagicMock(
            challenge_id="XBEN-001-24",
            passed=True,
            duration_seconds=0.0,
        )

        config = BenchmarkConfig(cleanup_workspaces=True)
        harness = Harness(provider=provider, config=config)
        harness._invoke_agent = AsyncMock(
            return_value=AgentResponse(text="No flag found", thread_id="test-thread")
        )
        challenge = _make_challenge(tmp_path)

        workspace_path = (Path.home() / f".decepticon/workspace/benchmark-{challenge.id}").resolve()

        await harness.run_challenge(challenge)

        assert not workspace_path.exists()

    @pytest.mark.asyncio
    async def test_teardown_on_error(self, tmp_path: Path) -> None:
        """Verify provider.teardown() is called even when an exception occurs."""
        provider = _make_provider()
        config = BenchmarkConfig(cleanup_workspaces=True)
        harness = Harness(provider=provider, config=config)
        harness._invoke_agent = AsyncMock(side_effect=RuntimeError("boom"))
        challenge = _make_challenge(tmp_path)

        with patch("benchmark.harness.time") as mock_time:
            mock_time.time.side_effect = [100.0, 100.42]

            result = await harness.run_challenge(challenge)

            provider.teardown.assert_called_once_with(challenge)
            assert result.passed is False
            assert result.error == "boom"
            assert result.duration_seconds == 0.42

    @pytest.mark.asyncio
    async def test_timeout_returns_failed(self, tmp_path: Path) -> None:
        """Verify that timeout produces a failed ChallengeResult with duration."""
        provider = _make_provider()
        config = BenchmarkConfig(timeout=1, cleanup_workspaces=True)
        harness = Harness(provider=provider, config=config)
        challenge = _make_challenge(tmp_path)

        async def _slow_agent(*args, **kwargs) -> AgentResponse:
            await asyncio.sleep(10)
            return AgentResponse(text="", thread_id="test-thread")

        harness._invoke_agent = _slow_agent

        result = await harness.run_challenge(challenge)

        assert result.passed is False
        assert "Timeout" in (result.error or "")
        assert result.duration_seconds > 0
        provider.teardown.assert_called_once_with(challenge)

    @pytest.mark.asyncio
    async def test_duration_tracked(self, tmp_path: Path) -> None:
        """Verify duration_seconds is set on successful result."""
        provider = _make_provider()
        provider.evaluate.return_value = MagicMock(
            challenge_id="XBEN-001-24",
            passed=False,
            duration_seconds=0.0,
        )

        config = BenchmarkConfig(cleanup_workspaces=True)
        harness = Harness(provider=provider, config=config)
        harness._invoke_agent = AsyncMock(
            return_value=AgentResponse(text="No flag found", thread_id="test-thread")
        )
        challenge = _make_challenge(tmp_path)

        with patch("benchmark.harness.time") as mock_time:
            mock_time.time.side_effect = [100.0, 100.0, 101.23]

            result = await harness.run_challenge(challenge)

            assert result.duration_seconds == 1.23

    @pytest.mark.asyncio
    async def test_flag_in_response_populates_state(self, tmp_path: Path) -> None:
        """Verify that FLAG{...} in agent response is passed to evaluate()."""
        provider = _make_provider()
        config = BenchmarkConfig(cleanup_workspaces=True)
        harness = Harness(provider=provider, config=config)
        challenge = _make_challenge(tmp_path)

        flag = "FLAG{abc123def456}"
        harness._invoke_agent = AsyncMock(
            return_value=AgentResponse(text=f"Found the flag: {flag}", thread_id="test-thread")
        )

        # Capture the state passed to evaluate
        captured_state = {}

        def mock_evaluate(ch, state, ws):
            captured_state["state"] = state
            return MagicMock(
                challenge_id=ch.id,
                passed=True,
                duration_seconds=0.0,
            )

        provider.evaluate = mock_evaluate

        await harness.run_challenge(challenge)

        state = captured_state["state"]
        assert len(state.iteration_history) >= 1
        assert flag in state.iteration_history[0].raw_output
        assert state.iteration_history[0].outcome == "PASSED"

    @pytest.mark.asyncio
    async def test_no_engagement_loop_used(self, tmp_path: Path) -> None:
        """Verify harness does NOT use EngagementLoop."""
        import benchmark.harness as harness_module

        assert not hasattr(harness_module, "EngagementLoop")

    def test_extract_message_from_runs_wait(self) -> None:
        """Verify _extract_message parses /runs/wait response format."""
        harness = Harness(provider=MagicMock(), config=BenchmarkConfig())

        # /runs/wait returns state with messages array
        data = {
            "messages": [
                {"type": "human", "content": "test prompt"},
                {"type": "ai", "content": "Found FLAG{abc123}"},
            ]
        }
        result = harness._extract_message(data)
        assert "FLAG{abc123}" in result

    def test_extract_message_handles_list_response(self) -> None:
        """Verify _extract_message handles list responses (state snapshots)."""
        harness = Harness(provider=MagicMock(), config=BenchmarkConfig())

        # /runs/wait may return a list of state snapshots
        data = [
            {"messages": [{"type": "human", "content": "prompt"}]},
            {
                "messages": [
                    {"type": "human", "content": "prompt"},
                    {"type": "ai", "content": "Found FLAG{abc123}"},
                ]
            },
        ]
        result = harness._extract_message(data)
        assert "FLAG{abc123}" in result

    def test_extract_message_handles_empty_list(self) -> None:
        """Verify _extract_message handles empty list response."""
        harness = Harness(provider=MagicMock(), config=BenchmarkConfig())
        result = harness._extract_message([])
        assert result == ""

    def test_extract_message_collects_all_ai_messages(self) -> None:
        """Verify _extract_message collects all AI messages (sub-agent responses)."""
        harness = Harness(provider=MagicMock(), config=BenchmarkConfig())

        data = {
            "messages": [
                {"type": "human", "content": "prompt"},
                {"type": "ai", "content": "Delegating to recon..."},
                {"type": "ai", "content": "Recon complete. Delegating to exploit..."},
                {"type": "ai", "content": "Exploit found FLAG{deadbeef}"},
            ]
        }
        result = harness._extract_message(data)
        assert "FLAG{deadbeef}" in result
        assert "Delegating to recon" in result
