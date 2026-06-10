"""Tests for benchmark.harness.Harness.

The infra-maintenance helpers (sandbox restart, service health gate) are
stubbed by the autouse ``stub_infra`` fixture below, so these tests run
fast and need neither docker nor live LangGraph/LiteLLM services. The
previously-required ``slow`` marker is gone — the suite runs in the PR
fast lane.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from benchmark.config import BenchmarkConfig
from benchmark.harness import AgentResponse, Harness, _ActiveRun
from benchmark.schemas import Challenge, SetupResult


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ``Path.home()`` to a per-test directory.

    Every test here builds a challenge with the same hardcoded id, and the
    harness derives its workspace from
    ``Path.home() / .decepticon/workspace/benchmark-<id>``. Without this
    isolation the tests share one workspace directory and race when run
    under ``pytest -n auto``.
    """
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path)


@pytest.fixture(autouse=True)
def stub_infra(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Stub the docker/service maintenance helpers on the Harness class.

    Without this, ``run_challenge`` shells out to docker and polls LiteLLM /
    LangGraph health endpoints for up to their full readiness budgets —
    which is what used to make this module a ~120s ``slow``-marked suite.
    """
    mocks = {
        "reset_sandbox": AsyncMock(),
        "ensure_healthy": AsyncMock(),
        "run_docker": AsyncMock(return_value=None),
    }
    monkeypatch.setattr(Harness, "_reset_sandbox_state", mocks["reset_sandbox"])
    monkeypatch.setattr(Harness, "_ensure_services_healthy", mocks["ensure_healthy"])
    monkeypatch.setattr(Harness, "_run_docker", mocks["run_docker"])
    return mocks


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
            return_value=AgentResponse(text="No flag found", trace_id="test-trace")
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
            return_value=AgentResponse(text="No flag found", trace_id="test-trace")
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
            # call order: run_start, agent_start, now (in except handler)
            mock_time.time.side_effect = [100.0, 100.0, 100.42]

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
            return AgentResponse(text="", trace_id="test-trace")

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
            return_value=AgentResponse(text="No flag found", trace_id="test-trace")
        )
        challenge = _make_challenge(tmp_path)

        with patch("benchmark.harness.time") as mock_time:
            # call order: run_start, agent_start, BenchmarkStepResult, now (success path)
            mock_time.time.side_effect = [100.0, 100.0, 101.23, 101.23]

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
            return_value=AgentResponse(text=f"Found the flag: {flag}", trace_id="test-trace")
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
        assert len(state.step_history) >= 1
        assert flag in state.step_history[0].raw_output
        assert state.step_history[0].outcome == "PASSED"

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

    @pytest.mark.skip(
        reason=(
            "Mock is too tightly coupled to langgraph_sdk internals (post() shape, "
            "response.aread, run_id extraction). Recent SDK upgrade requires a "
            "respx/MockAsync-based rewrite. Tracking separately."
        )
    )
    @pytest.mark.asyncio
    async def test_invoke_agent_passes_challenge_state_fields(self) -> None:
        """`_invoke_agent` must put benchmark context on the run state, not the human prompt."""
        captured: dict[str, object] = {}

        class _FakeResp:
            status_code = 200
            content = b'{"messages": [{"type": "ai", "content": "ok"}]}'
            text = '{"messages": [{"type": "ai", "content": "ok"}]}'
            headers: dict[str, str] = {"content-type": "application/json"}

            def raise_for_status(self) -> None: ...
            def json(self) -> dict[str, object]:
                return {"messages": [{"type": "ai", "content": "ok"}]}

            async def aread(self) -> bytes:
                return self.content

            async def aclose(self) -> None: ...

        class _FakeClient:
            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *_a: object) -> None:
                return None

            async def post(
                self,
                _url: str,
                json: dict[str, object] | None = None,
                **_kwargs: object,
            ) -> _FakeResp:
                # Absorb any extra kwargs (headers, params, etc.) the SDK adds
                # to its internal httpx.AsyncClient.post — the test only cares
                # about the json payload.
                captured["payload"] = json
                return _FakeResp()

        harness = Harness(provider=MagicMock(), config=BenchmarkConfig())
        challenge = Challenge(
            id="XBEN-042-24",
            name="Some Challenge",
            description="A test mission brief.",
            level=2,
            tags=["sqli", "auth-bypass"],
            compose_dir=Path("/tmp"),
        )

        with patch("benchmark.harness.httpx.AsyncClient", return_value=_FakeClient()):
            await harness._invoke_agent(
                challenge,
                target_url="http://host.docker.internal:33042",
                extra_ports={22: 2222},
                active=_ActiveRun(langgraph_url="http://localhost:2024"),
            )

        payload = captured["payload"]
        assert isinstance(payload, dict)
        input_state = payload["input"]
        assert isinstance(input_state, dict)

        # Challenge context flows via state, not the human prompt.
        assert input_state["target_url"] == "http://host.docker.internal:33042"
        assert input_state["target_extra_ports"] == {22: 2222}
        assert input_state["vulnerability_tags"] == ["sqli", "auth-bypass"]
        assert input_state["flag_format"] == "FLAG{<64-char-hex>}"
        assert "Some Challenge" in input_state["mission_brief"]
        assert input_state["engagement_name"] == "benchmark-XBEN-042-24"
        assert input_state["workspace_path"] == "/workspace/benchmark-XBEN-042-24"

        # Human message is minimal — per-challenge target details flow only
        # through state, not the human prompt. Mode detection itself is the
        # responsibility of EngagementContextMiddleware (BENCHMARK_MODE env);
        # the human message is just a kickoff trigger.
        messages = input_state["messages"]
        assert len(messages) == 1
        human_text = messages[0]["content"]
        assert "**Target URL:**" not in human_text
        assert challenge.name not in human_text
        assert challenge.description not in human_text

    @pytest.mark.asyncio
    async def test_pass_survives_teardown_failure(self, tmp_path: Path) -> None:
        """A PASS result must not be flipped to FAIL when teardown throws."""
        provider = _make_provider()
        provider.evaluate.return_value = MagicMock(
            challenge_id="XBEN-001-24",
            passed=True,
            duration_seconds=0.0,
        )
        provider.teardown.side_effect = RuntimeError("compose down exploded")

        harness = Harness(provider=provider, config=BenchmarkConfig(cleanup_workspaces=True))
        harness._invoke_agent = AsyncMock(
            return_value=AgentResponse(text="FLAG{deadbeef}", trace_id="test-trace")
        )

        result = await harness.run_challenge(_make_challenge(tmp_path))

        assert result.passed is True
        # Exactly one teardown attempt — no double-teardown via the
        # generic exception handler.
        provider.teardown.assert_called_once()

    @pytest.mark.asyncio
    async def test_submission_failure_records_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exhausted run-submission retries surface as ChallengeResult.error."""
        monkeypatch.setattr("benchmark.harness._SUBMIT_BACKOFF_SECONDS", 0)

        client = MagicMock()
        client.threads.create = AsyncMock(side_effect=ConnectionError("langgraph down"))
        monkeypatch.setattr("benchmark.harness.get_client", lambda *a, **kw: client)

        provider = _make_provider()
        harness = Harness(provider=provider, config=BenchmarkConfig(cleanup_workspaces=True))

        result = await harness.run_challenge(_make_challenge(tmp_path))

        assert result.passed is False
        assert "Run submission failed" in (result.error or "")
        assert client.threads.create.await_count == 3
        provider.teardown.assert_called_once()

    @pytest.mark.asyncio
    async def test_sandbox_reset_skipped_with_siblings_in_flight(
        self, tmp_path: Path, stub_infra: dict[str, AsyncMock]
    ) -> None:
        """Sandbox reset only fires when the challenge is the sole runner."""
        provider = _make_provider()
        provider.evaluate.return_value = MagicMock(
            challenge_id="XBEN-001-24", passed=True, duration_seconds=0.0
        )
        harness = Harness(provider=provider, config=BenchmarkConfig(cleanup_workspaces=True))
        harness._invoke_agent = AsyncMock(
            return_value=AgentResponse(text="ok", trace_id="test-trace")
        )
        challenge = _make_challenge(tmp_path)

        await harness.run_challenge(challenge)
        assert stub_infra["reset_sandbox"].await_count == 1

        # Simulate a sibling already running: the wrapper will bump the
        # counter to 2 and the reset must be skipped.
        harness._in_flight = 1
        await harness.run_challenge(challenge)
        assert stub_infra["reset_sandbox"].await_count == 1

    def test_scan_workspace_uses_challenge_pattern(self, tmp_path: Path) -> None:
        """Only files matching the challenge's flag pattern are collected."""
        harness = Harness(provider=MagicMock(), config=BenchmarkConfig())
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "hit.txt").write_text("found FLAG{deadbeef}")
        (ws / "miss.txt").write_text("FLAG{NOT-HEX-so-no-match}")
        (ws / "binary.bin").write_text("FLAG{deadbeef}")  # unscannable suffix

        challenge = _make_challenge(tmp_path)
        out = harness._scan_workspace_for_output(ws, challenge.flag_pattern)
        assert "FLAG{deadbeef}" in out
        assert "NOT-HEX" not in out

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
