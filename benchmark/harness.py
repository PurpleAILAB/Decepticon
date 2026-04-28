from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

from benchmark.config import BenchmarkConfig
from benchmark.providers.base import BaseBenchmarkProvider
from benchmark.schemas import Challenge, ChallengeResult
from decepticon.core.engagement import EngagementState, IterationResult

log = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Structured response from a LangGraph agent invocation."""

    text: str
    thread_id: str
    token_count: int | None = None


class Harness:
    """Runs benchmark challenges through the decepticon main agent.

    The decepticon agent handles the full kill chain:
      1. Reviews the pre-seeded OPPLAN
      2. Delegates to recon sub-agent via task() tool
      3. Delegates to exploit sub-agent via task() tool
      4. Captures the flag
    """

    def __init__(self, provider: BaseBenchmarkProvider, config: BenchmarkConfig) -> None:
        self.provider = provider
        self.config = config

    def _ensure_services_healthy(self) -> None:
        """Check LangGraph and LiteLLM are reachable with models loaded."""
        # Check LiteLLM: verify models are loaded via /v1/models endpoint
        litellm_url = self.config.langgraph_url.replace(":2024", ":4000")
        litellm_ready = False
        for attempt in range(30):
            try:
                r = httpx.get(
                    f"{litellm_url}/v1/models",
                    headers={"Authorization": "Bearer sk-decepticon-master"},
                    timeout=5,
                )
                if r.status_code == 200:
                    models = r.json().get("data", [])
                    if len(models) > 0:
                        log.info("LiteLLM ready with %d models", len(models))
                        litellm_ready = True
                        break
            except Exception:
                pass
            if attempt == 0:
                log.warning("LiteLLM not ready (waiting for models to initialize)...")
            time.sleep(4)
        if not litellm_ready:
            log.error("LiteLLM not fully initialized after 120s")

        # Check LangGraph
        try:
            r = httpx.get(f"{self.config.langgraph_url}/ok", timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass

        log.warning("LangGraph unreachable — restarting container")
        subprocess.run(
            ["docker", "compose", "up", "-d", "--no-deps", "langgraph"],
            capture_output=True,
        )
        # Reconnect networks (lost after container recreation)
        for net in ("benchmark_decepticon-net", "benchmark_sandbox-net"):
            subprocess.run(
                ["docker", "network", "connect", net, "decepticon-langgraph"],
                capture_output=True,
            )
        # Wait for LangGraph to become healthy
        for _ in range(30):
            time.sleep(2)
            try:
                r = httpx.get(f"{self.config.langgraph_url}/ok", timeout=5)
                if r.status_code == 200:
                    log.info("LangGraph restarted successfully")
                    return
            except Exception:
                pass
        log.error("LangGraph failed to restart after 60s")

    async def run_challenge(self, challenge: Challenge) -> ChallengeResult:
        # Use ~/.decepticon/workspace/ which is bind-mounted as /workspace/ in the sandbox
        workspace = (Path.home() / f".decepticon/workspace/benchmark-{challenge.id}").resolve()

        # Ensure LangGraph is alive before each challenge
        self._ensure_services_healthy()

        # Clean residual sandbox workspace from previous runs (sandbox is persistent)
        sandbox_ws = f"/workspace/benchmark-{challenge.id}"
        subprocess.run(
            ["docker", "exec", "decepticon-sandbox", "rm", "-rf", sandbox_ws],
            capture_output=True,
        )
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        (workspace / "plan").mkdir(parents=True, exist_ok=True)

        start = time.time()
        try:
            setup_result = self.provider.setup(challenge)
            if not setup_result.success:
                return ChallengeResult(
                    challenge_id=challenge.id,
                    challenge_name=challenge.name,
                    level=challenge.level,
                    tags=challenge.tags,
                    passed=False,
                    error=setup_result.error,
                    duration_seconds=round(time.time() - start, 2),
                )

            # Invoke decepticon main agent — handles full chain via SubAgentMiddleware
            # Agent creates its own OPPLAN based on challenge info
            extra_ports = setup_result.extra_ports
            agent_resp = await asyncio.wait_for(
                self._invoke_agent(challenge, setup_result.target_url, extra_ports),
                timeout=self.config.timeout,
            )

            # Build EngagementState from agent response for evaluate()
            state = EngagementState()
            state.iteration_history.append(
                IterationResult(
                    objective_id="OBJ-001",
                    agent_used="decepticon",
                    outcome="PASSED" if "FLAG{" in agent_resp.text else "BLOCKED",
                    raw_output=agent_resp.text,
                    duration_seconds=round(time.time() - start, 2),
                )
            )

            # Also scan workspace for any findings/outputs containing flags
            workspace_text = self._scan_workspace_for_output(workspace)
            if workspace_text:
                state.iteration_history.append(
                    IterationResult(
                        objective_id="OBJ-002",
                        agent_used="decepticon",
                        outcome="PASSED" if "FLAG{" in workspace_text else "BLOCKED",
                        raw_output=workspace_text,
                        duration_seconds=0.0,
                    )
                )

            result = self.provider.evaluate(challenge, state, workspace)
            result.duration_seconds = round(time.time() - start, 2)
            result.thread_id = agent_resp.thread_id
            result.token_count = agent_resp.token_count
            result.agent_summary = agent_resp.text[:500] if agent_resp.text else None
            return result

        except asyncio.TimeoutError:
            # Agent timed out, but may have written flags to workspace
            workspace_text = self._scan_workspace_for_output(workspace)
            if workspace_text and "FLAG{" in workspace_text:
                state = EngagementState()
                state.iteration_history.append(
                    IterationResult(
                        objective_id="OBJ-002",
                        agent_used="decepticon",
                        outcome="PASSED",
                        raw_output=workspace_text,
                        duration_seconds=round(time.time() - start, 2),
                    )
                )
                result = self.provider.evaluate(challenge, state, workspace)
                result.duration_seconds = round(time.time() - start, 2)
                return result

            return ChallengeResult(
                challenge_id=challenge.id,
                challenge_name=challenge.name,
                level=challenge.level,
                tags=challenge.tags,
                passed=False,
                error=f"Timeout after {self.config.timeout}s",
                duration_seconds=round(time.time() - start, 2),
            )
        except Exception as exc:
            return ChallengeResult(
                challenge_id=challenge.id,
                challenge_name=challenge.name,
                level=challenge.level,
                tags=challenge.tags,
                passed=False,
                error=str(exc),
                duration_seconds=round(time.time() - start, 2),
            )
        finally:
            self.provider.teardown(challenge)
            if self.config.cleanup_workspaces and workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)

    async def _invoke_agent(
        self,
        challenge: Challenge,
        target_url: str,
        extra_ports: dict[int, int] | None = None,
    ) -> AgentResponse:
        """Invoke the decepticon main agent to execute one benchmark run.

        Mode detection lives entirely in the LangGraph container's
        BENCHMARK_MODE env var. Per-run target context (target_url,
        vulnerability_tags, flag_format, mission_brief, target_extra_ports)
        is delivered via state fields, which EngagementContextMiddleware
        reinjects into the system prompt on every model call. The human
        message therefore stays mode-neutral — it only kicks off the
        operation. See decepticon/middleware/engagement_context.py.
        """
        # The sandbox maps ~/.decepticon/workspace/ → /workspace/
        sandbox_workspace = f"/workspace/benchmark-{challenge.id}"

        prompt = (
            "Begin the operation. Build the OPPLAN from your system context "
            "and execute it by delegating to the appropriate sub-agents via "
            "task(). Surface the final result in your final response text."
        )

        input_state: dict = {
            "messages": [{"role": "human", "content": prompt}],
            "engagement_name": f"benchmark-{challenge.id}",
            "workspace_path": sandbox_workspace,
            "target_url": target_url,
            "target_extra_ports": extra_ports or {},
            "vulnerability_tags": challenge.tags,
            "flag_format": "FLAG{<64-char-hex>}",
            "mission_brief": f"{challenge.name} — {challenge.description}",
        }

        thread_id = str(uuid.uuid4())
        url = f"{self.config.langgraph_url}/runs/wait"
        payload = {
            "assistant_id": "decepticon",
            "thread_id": thread_id,
            "input": input_state,
            "config": {
                "configurable": {
                    "workspace": sandbox_workspace,
                },
                "recursion_limit": 200,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.timeout + 30)) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            log.info(
                "Agent response type=%s keys=%s",
                type(data).__name__,
                list(data.keys())
                if isinstance(data, dict)
                else f"len={len(data)}"
                if isinstance(data, list)
                else "N/A",
            )
            text = self._extract_message(data)
            return AgentResponse(text=text, thread_id=thread_id)

        except httpx.ConnectError:
            log.warning(
                "Cannot reach LangGraph at %s — returning empty response",
                self.config.langgraph_url,
            )
            return AgentResponse(text="", thread_id=thread_id)
        except Exception as exc:
            log.warning("Agent invocation failed for %s: %s", challenge.id, exc)
            return AgentResponse(text="", thread_id=thread_id)

    def _extract_message(self, data: object) -> str:
        """Extract the final assistant message text from a LangGraph run response."""
        # /runs/wait may return a list (array of state snapshots) in some modes
        if isinstance(data, list):
            if data:
                # Take the last element (final state)
                data = data[-1]
            else:
                log.warning("Agent returned empty list response")
                return ""

        if not isinstance(data, dict):
            return str(data)

        # Handle LangGraph error responses: {"__error__": "..."}
        if "__error__" in data:
            error_detail = data["__error__"]
            log.error("Agent returned error: %s", error_detail)
            return ""

        # /runs/wait returns full state: {"messages": [...]}
        messages = data.get("messages", [])

        # Also check nested output format: {"output": {"messages": [...]}}
        if not messages:
            output = data.get("output")
            if isinstance(output, dict):
                messages = output.get("messages", [])

        if isinstance(messages, list):
            # Collect ALL assistant messages (sub-agent responses may contain the flag)
            all_content: list[str] = []
            for msg in messages:
                if isinstance(msg, dict) and msg.get("type") == "ai":
                    content = msg.get("content", "")
                    if isinstance(content, str) and content:
                        all_content.append(content)
                    elif isinstance(content, list):
                        parts = [
                            c.get("text", "")
                            for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        ]
                        text = " ".join(p for p in parts if p)
                        if text:
                            all_content.append(text)
            if all_content:
                return "\n\n".join(all_content)

        return json.dumps(data)

    def _scan_workspace_for_output(self, workspace: Path) -> str:
        """Scan workspace files for flag patterns recursively.

        The Docker sandbox creates files as root, so OSError (permission
        denied) is caught and silently skipped.
        """
        texts: list[str] = []
        flag_pattern = re.compile(r"FLAG\{[a-f0-9]+\}")
        scannable = {".md", ".txt", ".json", ".log", ".html", ".jsonl", ".csv"}

        if not workspace.is_dir():
            return ""

        for f in sorted(workspace.rglob("*")):
            if not f.is_file() or f.suffix not in scannable:
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if flag_pattern.search(content):
                    texts.append(content)
            except OSError:
                pass

        return "\n\n".join(texts)
