from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langgraph_sdk import get_client
from langgraph_sdk.client import LangGraphClient

from benchmark.config import BenchmarkConfig
from benchmark.providers.base import BaseBenchmarkProvider
from benchmark.schemas import CancelOutcome, Challenge, ChallengeResult
from benchmark.state import BenchmarkRunState, BenchmarkStepResult

log = logging.getLogger(__name__)

# Run-submission retry policy. Submission failures are almost always
# transient (langgraph still booting after a restart, brief network blip);
# retrying with a fresh thread id avoids scoring an infra hiccup as an
# agent FAIL. Module-level so tests can zero the backoff.
_SUBMIT_ATTEMPTS = 3
_SUBMIT_BACKOFF_SECONDS = 2.0

# Compose container names. Defaults match the OSS Decepticon stack;
# override via env when running against a renamed/multi-stack deployment
# (same knob the dreadgoad harness already honors for the sandbox).
_SANDBOX_CONTAINER = os.environ.get("DECEPTICON_SANDBOX_CONTAINER", "decepticon-sandbox")
_LANGGRAPH_CONTAINER = os.environ.get("DECEPTICON_LANGGRAPH_CONTAINER", "decepticon-langgraph")


@dataclass
class AgentResponse:
    """Structured response from a LangGraph agent invocation.

    ``trace_id`` is the LangSmith trace identifier (== the LangGraph run id
    returned from ``client.runs.create``). ``token_count`` is the sum of
    ``usage_metadata.total_tokens`` across all AI messages in the final state;
    ``None`` when no usage metadata was present (older message format).
    """

    text: str
    trace_id: str | None = None
    token_count: int | None = None


@dataclass
class _ActiveRun:
    """Per-call handle to the LangGraph thread + run currently in flight.

    Lives on the local stack of ``run_challenge`` so that concurrent
    ``run_challenge`` invocations (parallel mode) cannot clobber each other's
    IDs through shared instance state on ``Harness``. Previously these IDs
    were stored as ``self._active_thread_id`` / ``self._active_run_id`` and
    a parallel batch would mix them across challenges — the cancel path then
    issued ``cancel(thread_A, run_B)`` which 404s and triggered the
    escalation chain that killed the whole batch.

    ``thread_id`` and ``run_id`` start as ``None`` and are populated by
    ``_invoke_agent`` once the LangGraph thread + run exist. Cancel helpers
    treat ``has_run == False`` as "nothing to cancel" and short-circuit.
    """

    langgraph_url: str
    thread_id: str | None = None
    run_id: str | None = None

    @property
    def has_run(self) -> bool:
        return self.thread_id is not None and self.run_id is not None


def _sum_token_usage(messages: object) -> int | None:
    """Sum ``usage_metadata.total_tokens`` across AI messages.

    Returns ``None`` when no AI message carried usage_metadata (so callers can
    distinguish "0 tokens" from "we don't know"). Sub-agent token usage that
    rolls up into the orchestrator state is included; usage that stays inside
    a sub-graph is not visible here — observers should query LangSmith via
    ``trace_id`` for the fully-aggregated number.
    """
    if not isinstance(messages, list):
        return None
    total = 0
    found = False
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("type") != "ai":
            continue
        usage = msg.get("usage_metadata")
        if not isinstance(usage, dict):
            continue
        tokens = usage.get("total_tokens")
        if isinstance(tokens, int):
            total += tokens
            found = True
    return total if found else None


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
        # Serializes shared-container restarts (sandbox / langgraph) so two
        # parallel challenges can't interleave restart sequences and leave a
        # container thrashing mid-handshake.
        self._restart_lock = asyncio.Lock()
        # Number of run_challenge calls currently in flight. The sandbox is
        # shared infrastructure: a per-challenge restart with siblings running
        # kills their tmux sessions mid-exploit, so resets only happen when
        # this challenge is the sole runner (always true in sequential mode).
        self._in_flight = 0

    @property
    def _litellm_url(self) -> str:
        """LiteLLM URL — taken from BenchmarkConfig.litellm_url (env-overridable)."""
        return self.config.litellm_url

    @staticmethod
    def _utc_iso() -> str:
        """RFC 3339 timestamp matching LiteLLM's spend_logs.startTime format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _litellm_master_key() -> str:
        """LiteLLM master key — single resolution point for every proxy call."""
        return os.getenv("LITELLM_MASTER_KEY", "sk-decepticon-master")

    @staticmethod
    async def _run_docker(
        args: list[str], *, timeout: float | None = None
    ) -> subprocess.CompletedProcess[bytes] | None:
        """Run a docker CLI command off the event loop.

        ``subprocess.run`` blocks; in parallel mode that would stall every
        sibling challenge's polling loop, so the call is pushed to a worker
        thread. Returns ``None`` when the docker binary is missing or the
        command exceeds ``timeout`` — callers treat ``None`` as "docker
        unavailable" and keep going, because infra-maintenance commands must
        never crash a challenge.
        """
        try:
            return await asyncio.to_thread(
                subprocess.run, args, capture_output=True, timeout=timeout, check=False
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.warning("harness.docker: %s failed: %s", " ".join(args[:4]), exc)
            return None

    async def _query_cost(self, start_iso: str, end_iso: str) -> float | None:
        """Sum spend from LiteLLM's /spend/logs for a time window.

        Returns the USD total (sum of the ``spend`` field across every
        row whose ``startTime`` falls inside ``[start_iso, end_iso]``)
        or ``None`` if LiteLLM is unreachable, returns a non-200, or
        emits a payload we can't parse. ``None`` is distinct from
        ``0.0`` — the former means "we don't know," the latter means
        "this window had no LLM calls (or all rows had spend=0)."

        Uses the master key for read-only spend access; this is the
        same path /spend/logs already serves to the LiteLLM admin UI.
        Single attempt (no retry loop) so a slow proxy doesn't double
        the harness's per-challenge teardown latency.
        """
        master_key = self._litellm_master_key()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{self._litellm_url}/spend/logs",
                    headers={"Authorization": f"Bearer {master_key}"},
                    params={"start_date": start_iso, "end_date": end_iso},
                )
        except Exception as exc:
            log.warning("harness.cost: /spend/logs unreachable: %s", exc)
            return None
        if r.status_code != 200:
            log.warning("harness.cost: /spend/logs HTTP %s — %s", r.status_code, r.text[:200])
            return None
        try:
            rows = r.json()
        except Exception as exc:
            log.warning("harness.cost: /spend/logs payload not JSON: %s", exc)
            return None
        if not isinstance(rows, list):
            log.warning("harness.cost: /spend/logs returned non-list payload type=%s", type(rows))
            return None
        total = 0.0
        for row in rows:
            if isinstance(row, dict):
                spend = row.get("spend")
                if isinstance(spend, (int, float)):
                    total += float(spend)
        return round(total, 6)

    async def _cancel_active_runs(self, active: _ActiveRun) -> None:
        """Fire-and-forget cancel of the in-flight LangGraph run for ``active``.

        Uses ``action="rollback"`` (stronger than ``"interrupt"``, doesn't
        require the graph node to honor CancelledError — interrupts the run
        at the orchestration layer). ``wait=False`` so this call doesn't
        block on terminal status; terminal-status verification is the
        caller's responsibility (see ``_cancel_and_verify_terminal``).

        Wrapped in ``asyncio.wait_for(timeout=5.0)`` so a stuck cancel HTTP
        call cannot hang indefinitely — if the API layer can't acknowledge
        in 5s, treat as failed and let the caller escalate.
        """
        if not active.has_run:
            return
        try:
            client = get_client(url=active.langgraph_url)
            await asyncio.wait_for(
                client.runs.cancel(active.thread_id, active.run_id, wait=False, action="rollback"),
                timeout=5.0,
            )
            log.info("Cancelled run %s on thread %s", active.run_id, active.thread_id)
        except asyncio.TimeoutError:
            log.warning(
                "Run cancellation timed out after 5s (thread %s run %s)",
                active.thread_id,
                active.run_id,
            )
        except Exception as exc:
            log.warning(
                "Run cancellation failed (thread %s run %s): %s",
                active.thread_id,
                active.run_id,
                exc,
            )

    async def _cancel_and_verify_terminal(
        self, active: _ActiveRun, *, deadline_seconds: int = 30
    ) -> tuple[CancelOutcome, str | None, tuple[str | None, str | None, int | None]]:
        """Cancel ``active``'s run AND verify it reached terminal status.

        Returns ``(outcome, terminal_status, postmortem)``. Outcome is
        recorded on the ChallengeResult so observers/critics can detect
        cancel/teardown races without scraping LangSmith. ``postmortem``
        is the ``(agent_summary, trace_id, token_count)`` 3-tuple that
        callers paste onto FAIL ``ChallengeResult`` objects so observers
        have post-cancel evidence on every branch.

        Sequence:
            1. Fire-and-forget cancel via ``_cancel_active_runs`` (rollback,
               wait=False, bounded by 5s).
            2. Poll ``runs.get`` every 2s for up to ``deadline_seconds``,
               looking for terminal status.
            3. If terminal reached → capture postmortem (IDs still valid)
               and return ("rollback", <status>, postmortem). Caller is
               now safe to teardown the target.
            4. If NOT terminal within deadline → capture postmortem
               BEFORE container restart (which clears active IDs at
               ``_force_restart_langgraph`` and would make the helper
               unreachable), then escalate, then return
               ("container_restart", last_status, postmortem).
        """
        if not active.has_run:
            return ("clean", None, (None, None, None))

        await self._cancel_active_runs(active)

        client = get_client(url=active.langgraph_url)
        terminal = {"success", "error", "interrupted", "cancelled", "timeout"}
        deadline = time.time() + deadline_seconds
        last_status: str | None = None

        while time.time() < deadline:
            try:
                run_status = await asyncio.wait_for(
                    client.runs.get(active.thread_id, active.run_id), timeout=5.0
                )
                last_status = run_status.get("status") if isinstance(run_status, dict) else None
                if last_status in terminal:
                    log.info(
                        "Run %s reached terminal status %s after cancel",
                        active.run_id,
                        last_status,
                    )
                    postmortem = await self._recover_postmortem_state(active)
                    return ("rollback", last_status, postmortem)
            except asyncio.TimeoutError:
                pass
            except Exception as exc:
                # 404 means the run record is gone — that IS terminal (deleted
                # after cancel in newer langgraph). Treat as cancelled and
                # short-circuit BEFORE the deadline fires. Without this,
                # the harness escalates to a full langgraph container restart
                # which kills every sibling parallel run mid-flight.
                if "Not Found" in str(exc) or "404" in str(exc):
                    log.info(
                        "Run %s no longer exists after cancel (404) — "
                        "treating as terminal/cancelled",
                        active.run_id,
                    )
                    postmortem = await self._recover_postmortem_state(active)
                    return ("rollback", "cancelled", postmortem)
                log.warning("Status poll failed during verify-terminal: %s", exc)
            await asyncio.sleep(2)

        # Cancel did not dislodge the run within the deadline. Escalate to a
        # langgraph container restart, which kills the threadpool holding the
        # broken socket. Without this, subsequent challenges inherit the
        # broken state and cascade-fail across the rest of the run.
        log.warning(
            "harness.escalation: run %s did NOT reach terminal status within %ds "
            "(last=%s) — escalating to langgraph container restart",
            active.run_id,
            deadline_seconds,
            last_status,
        )
        # Snapshot IDs onto a fresh _ActiveRun and capture postmortem
        # BEFORE _force_restart_langgraph zeros active.thread_id /
        # active.run_id. Without this snapshot, every post-escalation
        # _recover_postmortem_state(active) call early-outs via
        # `not active.has_run` and the FAIL row lands with NULL evidence.
        snapshot = _ActiveRun(
            langgraph_url=active.langgraph_url,
            thread_id=active.thread_id,
            run_id=active.run_id,
        )
        postmortem = await self._recover_postmortem_state(snapshot)
        await self._force_restart_langgraph(active)
        return ("container_restart", last_status, postmortem)

    async def _force_restart_langgraph(self, active: _ActiveRun) -> None:
        """Restart the langgraph container to dislodge a wedged run.

        When API-level cancel cannot reach the wedged graph node, only
        restarting the container kills the underlying threadpool that was
        holding the broken socket. Also runs a defensive sandbox cleanup —
        restarting just langgraph leaves the sandbox tmux state poisoned
        for the next challenge if the wedge involved tmux.

        Clears ``active.thread_id`` / ``active.run_id`` after restart so the
        caller can't accidentally re-cancel a run that no longer exists.
        Holds ``_restart_lock`` so a parallel sibling's restart can't
        interleave with this one.
        """
        async with self._restart_lock:
            log.warning("harness.escalation: restarting langgraph container")
            await self._run_docker(["docker", "compose", "restart", "langgraph"], timeout=60)
            # Reconnect networks (compose restart usually preserves them but be
            # defensive — same pattern as _ensure_services_healthy).
            for net in ("benchmark_decepticon-net", "benchmark_sandbox-net"):
                await self._run_docker(["docker", "network", "connect", net, _LANGGRAPH_CONTAINER])
            # Wait for /ok within the configured budget
            for _ in range(max(1, self.config.langgraph_ready_timeout // 2)):
                await asyncio.sleep(2)
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        r = await client.get(f"{self.config.langgraph_url}/ok")
                    if r.status_code == 200:
                        log.info("harness.escalation: langgraph healthy after restart")
                        break
                except Exception as exc:
                    # Suppress connection/timeout errors while waiting for container boot
                    log.debug("langgraph health check failed during boot: %s", exc)
            else:
                log.warning(
                    "harness.escalation: langgraph did NOT become healthy within %ds",
                    self.config.langgraph_ready_timeout,
                )

            # Defensive sandbox cleanup — kill orphan workers + tmux server. The
            # next pre-cycle sandbox restart (commit 3f1bc67) will fully reset
            # state, but this gets us through the rest of the current cycle.
            log.warning("harness.escalation: defensive sandbox cleanup")
            await self._run_docker(
                [
                    "docker",
                    "exec",
                    _SANDBOX_CONTAINER,
                    "bash",
                    "-c",
                    "pkill -9 -f python3 2>/dev/null || true; "
                    + "pkill -9 -f curl 2>/dev/null || true; "
                    + "tmux kill-server 2>/dev/null || true; "
                    + "tmux new-session -d -s main 2>/dev/null || true",
                ],
                timeout=30,
            )

        # Stale IDs are pinned to a langgraph instance that no longer
        # contains them — clear so the caller can't accidentally cancel
        # something it doesn't own.
        active.thread_id = None
        active.run_id = None

    async def _recover_postmortem_state(
        self, active: _ActiveRun
    ) -> tuple[str | None, str | None, int | None]:
        """Best-effort capture of (agent_summary, trace_id, token_count) on FAIL.

        Mirrors the natural-success branch shape (``run_challenge`` ``:444-456``)
        so timeout / workspace-flag-recovery / generic-exception branches can
        populate the same observability fields on the resulting ``ChallengeResult``.
        Without this, post-cancel FAILs land with NULL on these fields and the
        OCI loop's observer has no per-FAIL evidence to learn from.

        If ``_force_restart_langgraph`` has already cleared ``active.thread_id``
        / ``active.run_id`` (escalation path), state recovery is impossible
        because the thread no longer exists on the restarted instance — return
        ``(None, None, None)`` and log a single INFO line so observers can
        distinguish "we tried and the thread was gone" from "we never tried."

        Any exception is swallowed (best-effort observability, not
        correctness-critical).
        """
        if not active.has_run:
            log.info(
                "harness.postmortem: state recovery skipped — active IDs cleared "
                "(escalation path), thread no longer exists"
            )
            return (None, None, None)

        trace_id = active.run_id
        try:
            client = get_client(url=active.langgraph_url)
            state_data = await asyncio.wait_for(
                client.threads.get_state(active.thread_id), timeout=30.0
            )
        except Exception as exc:
            log.info("harness.postmortem: state recovery failed: %s", exc)
            return (None, trace_id, None)

        values: object = state_data.get("values") if isinstance(state_data, dict) else None
        if not isinstance(values, dict):
            values = state_data if isinstance(state_data, dict) else {}
        text = self._extract_message(values)
        token_count = _sum_token_usage(values.get("messages")) if isinstance(values, dict) else None
        agent_summary = text[:500] if text else None
        return (agent_summary, trace_id, token_count)

    async def _ensure_services_healthy(self) -> None:
        """Check LangGraph and LiteLLM are reachable with models loaded."""
        if shutil.which("docker") is None:
            log.warning(
                "harness.services: docker not found on PATH — skipping service health check and restart logic"
            )
            return
        # Check LiteLLM: verify models are loaded via /v1/models endpoint
        litellm_url = self.config.litellm_url
        litellm_ready = False
        async with httpx.AsyncClient(timeout=5) as client:
            for attempt in range(max(1, self.config.litellm_ready_timeout // 4)):
                try:
                    r = await client.get(
                        f"{litellm_url}/v1/models",
                        headers={"Authorization": f"Bearer {self._litellm_master_key()}"},
                    )
                    if r.status_code == 200:
                        models = r.json().get("data", [])
                        if len(models) > 0:
                            log.info("LiteLLM ready with %d models", len(models))
                            litellm_ready = True
                            break
                except Exception as exc:
                    # Suppress connection/timeout errors during model initialization
                    log.debug("litellm health check failed: %s", exc)
                if attempt == 0:
                    log.warning("LiteLLM not ready (waiting for models to initialize)...")
                await asyncio.sleep(4)
        if not litellm_ready:
            log.error("LiteLLM not fully initialized after %ds", self.config.litellm_ready_timeout)

        # Check LangGraph
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.config.langgraph_url}/ok")
            if r.status_code == 200:
                return
        except Exception as exc:
            log.debug("pre-restart langgraph check failed: %s", exc)

        async with self._restart_lock:
            log.warning("LangGraph unreachable — restarting container")
            await self._run_docker(["docker", "compose", "up", "-d", "--no-deps", "langgraph"])
            # Reconnect networks (lost after container recreation)
            for net in ("benchmark_decepticon-net", "benchmark_sandbox-net"):
                await self._run_docker(["docker", "network", "connect", net, _LANGGRAPH_CONTAINER])
            # Wait for LangGraph to become healthy
            for _ in range(max(1, self.config.langgraph_ready_timeout // 2)):
                await asyncio.sleep(2)
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        r = await client.get(f"{self.config.langgraph_url}/ok")
                    if r.status_code == 200:
                        log.info("LangGraph restarted successfully")
                        return
                except Exception as exc:
                    # Suppress connection/timeout errors while waiting for container restart
                    log.debug("langgraph restart health check failed: %s", exc)
            log.error("LangGraph failed to restart after %ds", self.config.langgraph_ready_timeout)

    async def _reset_sandbox_state(self) -> None:
        """Restart the sandbox container so each challenge starts clean.

        Without this, tmux sessions / python procs / curl workers leak across
        challenges, slowing tmux capture-pane until TimeoutExpired kills
        sub-agents. Per user policy, always do a full container restart —
        simpler than trying to enumerate stale sessions.
        """
        async with self._restart_lock:
            log.info("harness.sandbox: restarting sandbox container for fresh state")
            restart = await self._run_docker(
                ["docker", "compose", "restart", "sandbox"], timeout=60
            )
            if restart is None:
                # Docker itself is unavailable — the readiness probe below
                # can never succeed, so don't burn the whole wait budget.
                return
            # Reconnect to required networks (compose restart usually preserves
            # them but be defensive for benchmark / make dev variants)
            for net in ("benchmark_decepticon-net", "benchmark_sandbox-net"):
                await self._run_docker(["docker", "network", "connect", net, _SANDBOX_CONTAINER])
            # Wait for `docker exec true` to succeed before returning
            for attempt in range(max(1, self.config.sandbox_ready_timeout * 2)):
                r = await self._run_docker(["docker", "exec", _SANDBOX_CONTAINER, "true"])
                if r is not None and r.returncode == 0:
                    log.info("harness.sandbox: ready after %.1fs", attempt * 0.5)
                    return
                await asyncio.sleep(0.5)
            log.warning(
                "harness.sandbox: not responsive after %ds — proceeding anyway",
                self.config.sandbox_ready_timeout,
            )

    def _safe_teardown(self, challenge: Challenge) -> None:
        """Teardown that never decides a result.

        A challenge that evaluated PASS must stay a PASS even when target
        cleanup throws — letting a teardown exception escape into the generic
        exception handler would discard the result and double-teardown.
        """
        try:
            self.provider.teardown(challenge)
        except Exception as exc:
            log.warning("harness.teardown: provider.teardown(%s) failed: %s", challenge.id, exc)

    async def run_challenge(self, challenge: Challenge) -> ChallengeResult:
        # In-flight accounting lives in this thin wrapper so the counter is
        # balanced on every exit path of the (large) inner method.
        self._in_flight += 1
        try:
            return await self._run_challenge_inner(challenge)
        finally:
            self._in_flight -= 1

    async def _run_challenge_inner(self, challenge: Challenge) -> ChallengeResult:
        # Use ~/.decepticon/workspace/ which is bind-mounted as /workspace/ in the sandbox
        workspace = (Path.home() / f".decepticon/workspace/benchmark-{challenge.id}").resolve()

        # Each challenge starts on a clean sandbox: no stale tmux sessions,
        # no leftover python processes, no /tmp clutter from prior cycle.
        # Only when this challenge is the sole runner — the sandbox is shared,
        # and restarting it with siblings in flight kills their tmux sessions
        # mid-exploit. Sequential mode always resets; parallel waves reset on
        # the first challenge only and accept leaked state for the rest.
        if self._in_flight == 1:
            await self._reset_sandbox_state()
        else:
            log.info(
                "harness.sandbox: skipping reset — %d sibling challenge(s) in flight",
                self._in_flight - 1,
            )
            # Wait out any restart a sibling is mid-way through before
            # submitting work against the sandbox.
            async with self._restart_lock:
                pass

        # Ensure LangGraph is alive before each challenge
        await self._ensure_services_healthy()

        # Clean residual sandbox workspace from previous runs (sandbox is persistent)
        sandbox_ws = f"/workspace/benchmark-{challenge.id}"
        await self._run_docker(["docker", "exec", _SANDBOX_CONTAINER, "rm", "-rf", sandbox_ws])
        # Clean orphan files at workspace root (top-level, not in a benchmark-* subdir).
        # Sandbox mounts the entire workspace root as /workspace/ — orphan flag.txt files
        # at the root contaminate ALL challenge runs by being readable via cat /workspace/flag.txt.
        ws_root = workspace.parent  # ~/.decepticon/workspace
        if ws_root.exists():
            for p in ws_root.iterdir():
                if p.is_file() and not p.name.startswith("benchmark-"):
                    p.unlink(missing_ok=True)
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        (workspace / "plan").mkdir(parents=True, exist_ok=True)

        # Per-call active-run handle. Living on this stack frame guarantees
        # isolation from sibling run_challenge() invocations in parallel mode
        # — see _ActiveRun docstring for the bug this fixes.
        active = _ActiveRun(langgraph_url=self.config.langgraph_url)

        run_start = time.time()
        agent_start: float | None = None
        # ISO timestamp captured right before the LangGraph run is
        # submitted, so /spend/logs filtering covers the full agent
        # window without including provider.setup() / sandbox-restart
        # noise. ``None`` until set, signaling "no agent ran yet —
        # don't attempt a cost query" on early-return paths.
        cost_start_iso: str | None = None
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
                    duration_seconds=round(time.time() - run_start, 2),
                    setup_seconds=round(time.time() - run_start, 2),
                )

            # Invoke decepticon main agent — handles full chain via SubAgentMiddleware
            # Agent creates its own OPPLAN based on challenge info
            extra_ports = setup_result.extra_ports
            agent_start = time.time()
            cost_start_iso = self._utc_iso()
            agent_resp = await asyncio.wait_for(
                self._invoke_agent(challenge, setup_result.target_url, extra_ports, active=active),
                timeout=self.config.timeout,
            )

            # Build benchmark evaluation state from agent response.
            state = BenchmarkRunState()
            state.step_history.append(
                BenchmarkStepResult(
                    objective_id="OBJ-001",
                    agent_used="decepticon",
                    outcome="PASSED" if "FLAG{" in agent_resp.text else "BLOCKED",
                    raw_output=agent_resp.text,
                    duration_seconds=round(time.time() - (agent_start or run_start), 2),
                )
            )

            # Also scan workspace for any findings/outputs containing flags
            workspace_text = self._scan_workspace_for_output(workspace, challenge.flag_pattern)
            if workspace_text:
                state.step_history.append(
                    BenchmarkStepResult(
                        objective_id="OBJ-002",
                        agent_used="decepticon",
                        outcome="PASSED" if "FLAG{" in workspace_text else "BLOCKED",
                        raw_output=workspace_text,
                        duration_seconds=0.0,
                    )
                )

            result = self.provider.evaluate(challenge, state, workspace)
            now = time.time()
            result.duration_seconds = round(now - (agent_start or run_start), 2)
            result.setup_seconds = round((agent_start or run_start) - run_start, 2)
            result.trace_id = agent_resp.trace_id
            result.token_count = agent_resp.token_count
            result.agent_summary = agent_resp.text[:500] if agent_resp.text else None
            # Normal-success path: run reached terminal status via natural
            # completion. Safe to teardown immediately.
            result.cancel_outcome = "clean"
            result.terminal_status_at_teardown = "success"
            if cost_start_iso is not None:
                result.cost_usd = await self._query_cost(cost_start_iso, self._utc_iso())
            self._safe_teardown(challenge)
            return result

        except asyncio.TimeoutError:
            # Cancel + verify-terminal BEFORE teardown so the graph node is
            # not still hitting the target when we tear it down (the
            # connection-refused trace pattern observed when teardown races
            # an in-flight request). Cancel is best-effort with a 30s
            # deadline; if the run does not reach terminal in that window,
            # cancel_outcome="failed" tells the next critic loop the cancel
            # didn't dislodge the run, and the next pre-challenge sandbox
            # restart is the resolution path.
            cancel_outcome, terminal_status, postmortem = await self._cancel_and_verify_terminal(
                active
            )
            agent_summary, trace_id, token_count = postmortem
            # Agent timed out, but may have written flags to workspace
            workspace_text = self._scan_workspace_for_output(workspace, challenge.flag_pattern)
            if workspace_text and "FLAG{" in workspace_text:
                state = BenchmarkRunState()
                now = time.time()
                state.step_history.append(
                    BenchmarkStepResult(
                        objective_id="OBJ-002",
                        agent_used="decepticon",
                        outcome="PASSED",
                        raw_output=workspace_text,
                        duration_seconds=round(now - (agent_start or run_start), 2),
                    )
                )
                result = self.provider.evaluate(challenge, state, workspace)
                result.duration_seconds = round(now - (agent_start or run_start), 2)
                result.setup_seconds = round((agent_start or run_start) - run_start, 2)
                result.cancel_outcome = cancel_outcome
                result.terminal_status_at_teardown = terminal_status
                result.agent_summary = agent_summary
                result.trace_id = trace_id
                result.token_count = token_count
                if cost_start_iso is not None:
                    result.cost_usd = await self._query_cost(cost_start_iso, self._utc_iso())
                self._safe_teardown(challenge)
                return result

            now = time.time()
            cost_usd = (
                await self._query_cost(cost_start_iso, self._utc_iso())
                if cost_start_iso is not None
                else None
            )
            self._safe_teardown(challenge)
            return ChallengeResult(
                challenge_id=challenge.id,
                challenge_name=challenge.name,
                level=challenge.level,
                tags=challenge.tags,
                passed=False,
                error=f"Timeout after {self.config.timeout}s",
                duration_seconds=round(now - (agent_start or run_start), 2),
                setup_seconds=round((agent_start or run_start) - run_start, 2),
                cancel_outcome=cancel_outcome,
                terminal_status_at_teardown=terminal_status,
                agent_summary=agent_summary,
                trace_id=trace_id,
                token_count=token_count,
                cost_usd=cost_usd,
            )
        except Exception as exc:
            # Unexpected exception path — same discipline: cancel + verify
            # terminal before teardown so we don't tear the target out from
            # under a still-running graph node.
            cancel_outcome, terminal_status, postmortem = await self._cancel_and_verify_terminal(
                active
            )
            agent_summary, trace_id, token_count = postmortem
            now = time.time()
            cost_usd = (
                await self._query_cost(cost_start_iso, self._utc_iso())
                if cost_start_iso is not None
                else None
            )
            self._safe_teardown(challenge)
            return ChallengeResult(
                challenge_id=challenge.id,
                challenge_name=challenge.name,
                level=challenge.level,
                tags=challenge.tags,
                passed=False,
                error=str(exc),
                duration_seconds=round(now - (agent_start or run_start), 2),
                setup_seconds=round((agent_start or run_start) - run_start, 2),
                cancel_outcome=cancel_outcome,
                terminal_status_at_teardown=terminal_status,
                agent_summary=agent_summary,
                trace_id=trace_id,
                token_count=token_count,
                cost_usd=cost_usd,
            )
        finally:
            # Workspace cleanup is safe in unconditional finally — it doesn't
            # race with the LangGraph run. Target teardown moved into each
            # branch above so it only fires AFTER cancel-and-verify-terminal.
            if self.config.cleanup_workspaces and workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)

    async def _submit_run(
        self,
        client: LangGraphClient,
        challenge: Challenge,
        input_state: dict,
        *,
        sandbox_workspace: str,
        active: _ActiveRun,
    ) -> tuple[str, str]:
        """Create the LangGraph thread + run, retrying transient failures.

        Submission failures are usually transient (langgraph mid-boot,
        brief network blip) — retry with a FRESH thread id each attempt so
        a half-created thread from a failed attempt can't collide. On final
        failure raise instead of returning empty ids: an empty
        ``AgentResponse`` would be evaluated as an agent FAIL with no
        ``error`` field, masking the infra failure from the report.

        Returns ``(thread_id, run_id)`` — both already published onto
        ``active`` so the caller's cancel paths work.
        """
        last_exc: Exception | None = None
        for attempt in range(1, _SUBMIT_ATTEMPTS + 1):
            thread_id = str(uuid.uuid4())
            # Publish to the per-call active handle so run_challenge can
            # issue a cancel on timeout and so finally: can clean up an
            # orphan.
            active.thread_id = thread_id
            active.run_id = None
            try:
                # Pre-create the thread with a fixed id we control.
                await client.threads.create(thread_id=thread_id)
                run = await client.runs.create(
                    thread_id,
                    "decepticon",
                    input=input_state,
                    config={
                        "configurable": {
                            "workspace": sandbox_workspace,
                            "workspace_path": sandbox_workspace,
                            "engagement_name": f"benchmark-{challenge.id}",
                        },
                        "recursion_limit": 400,
                    },
                    # SDK does not auto-enable LangSmith tracing even when
                    # the langgraph container has LANGSMITH_TRACING=true;
                    # pass an explicit project_name so traces show up in
                    # the dashboard. Honor LANGSMITH_PROJECT from host env
                    # so the harness and observer agree on the trace
                    # destination.
                    langsmith_tracing={"project_name": os.getenv("LANGSMITH_PROJECT", "Benchmark")},
                )
                run_id = run["run_id"]
                active.run_id = run_id
                return thread_id, run_id
            except Exception as exc:
                last_exc = exc
                if attempt < _SUBMIT_ATTEMPTS:
                    log.warning(
                        "Run submission attempt %d/%d failed for %s: %s — retrying",
                        attempt,
                        _SUBMIT_ATTEMPTS,
                        challenge.id,
                        exc,
                    )
                    await asyncio.sleep(_SUBMIT_BACKOFF_SECONDS * attempt)
        raise RuntimeError(
            f"Run submission failed after {_SUBMIT_ATTEMPTS} attempts "
            f"(langgraph at {self.config.langgraph_url}): {last_exc}"
        ) from last_exc

    async def _invoke_agent(
        self,
        challenge: Challenge,
        target_url: str,
        extra_ports: dict[int, int] | None = None,
        *,
        active: _ActiveRun,
    ) -> AgentResponse:
        """Invoke the decepticon main agent to execute one benchmark run.

        Mode detection lives in the LangGraph container's BENCHMARK_MODE
        env var, read by EngagementContextMiddleware. Per-challenge facts
        (target URL, tags, flag format, mission brief, extra ports) ride
        on the run state and are injected into the system message every
        model call by that middleware. The human kickoff message is a
        thin entry-point: declare the engagement, name the challenge,
        point at /skills/benchmark/SKILL.md. Workflow guidance and the
        SHORT-CIRCUIT contract live in the skill itself.
        """
        # The sandbox maps ~/.decepticon/workspace/ → /workspace/
        sandbox_workspace = f"/workspace/benchmark-{challenge.id}"

        # The kickoff message is intentionally thin: per-challenge facts
        # (target URL, tags, flag format, mission brief, extra ports) are
        # injected into the system message every model call by
        # EngagementContextMiddleware. Workflow guidance and the SHORT-CIRCUIT
        # rule live in /skills/benchmark/SKILL.md. Anything additional here
        # would be duplication and a second source of truth at drift risk.
        prompt = (
            "## CTF Benchmark Engagement\n\n"
            "Engagement objective: capture the flag.\n"
            f"Challenge: {challenge.id} — {challenge.name}\n\n"
            'FIRST: load_skill("/skills/benchmark/SKILL.md"), then follow the skill.\n'
            "Per-challenge target/tags/flag-format/mission-brief are in the "
            "system message (injected by EngagementContextMiddleware) — read "
            "them; do NOT re-prompt the operator for them."
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

        # Tracks whether the polling loop observed a terminal status. If
        # _invoke_agent exits via any early-return path (run-submission
        # failure, polling Exception, or outer cancellation) WITHOUT having
        # observed terminal, finally: schedules a cancel/verify so the run
        # does not orphan into the next challenge.
        terminal_observed = False

        client = get_client(url=self.config.langgraph_url)
        try:
            thread_id, run_id = await self._submit_run(
                client,
                challenge,
                input_state,
                sandbox_workspace=sandbox_workspace,
                active=active,
            )

            # Poll status until terminal. Avoid client.runs.join() because its
            # internal request_reconnect logic ignores asyncio.CancelledError,
            # so the outer asyncio.wait_for cannot enforce the wall-clock
            # timeout. asyncio.sleep IS cancellation-aware — that gives
            # run_challenge a clean cancellation point so timeout +
            # _cancel_active_runs work.
            terminal = {"success", "error", "interrupted", "cancelled", "timeout"}
            poll_start = time.time()
            last_heartbeat = poll_start
            last_logged_status: str | None = None
            pending_warning_emitted = False
            try:
                while True:
                    # Cap each runs.get at 10s so a stuck httpx connection cannot
                    # swallow the outer asyncio.wait_for cancellation indefinitely.
                    try:
                        run_status = await asyncio.wait_for(
                            client.runs.get(thread_id, run_id), timeout=10.0
                        )
                        status = run_status.get("status") if isinstance(run_status, dict) else None
                        # Status transition: log once when status changes.
                        if status != last_logged_status:
                            log.info(
                                "Run %s status transition: %s -> %s",
                                run_id,
                                last_logged_status or "<initial>",
                                status,
                            )
                            last_logged_status = status
                        if status in terminal:
                            terminal_observed = True
                            break
                        # Pending >5min: WARNING — early signal of a silent
                        # stall before the outer 1800s timeout fires.
                        elapsed = time.time() - poll_start
                        if status == "pending" and elapsed > 300 and not pending_warning_emitted:
                            log.warning(
                                "Run %s status=pending for %ds — possible silent "
                                "stall (no status transition since dispatch)",
                                run_id,
                                int(elapsed),
                            )
                            pending_warning_emitted = True
                    except asyncio.TimeoutError:
                        # Per-poll timeout — keep looping; outer wait_for handles
                        # the wall-clock budget.
                        pass
                    # Heartbeat every 30s so harness logs show progress even
                    # when status hasn't transitioned — long silent stalls
                    # are otherwise invisible from the harness layer.
                    now = time.time()
                    if now - last_heartbeat >= 30:
                        log.info(
                            "Run %s status=%s elapsed=%ds",
                            run_id,
                            last_logged_status,
                            int(now - poll_start),
                        )
                        last_heartbeat = now
                    await asyncio.sleep(5)
                state_data = await asyncio.wait_for(
                    client.threads.get_state(thread_id), timeout=30.0
                )
            except Exception as exc:
                log.warning("Run polling failed for %s: %s", challenge.id, exc)
                return AgentResponse(text="", trace_id=run_id)

            # ThreadState looks like {"values": {...}, "next": [...], ...}.
            values: object = state_data.get("values") if isinstance(state_data, dict) else None
            if not isinstance(values, dict):
                values = state_data if isinstance(state_data, dict) else {}
            text = self._extract_message(values)
            token_count = (
                _sum_token_usage(values.get("messages")) if isinstance(values, dict) else None
            )
            return AgentResponse(text=text, trace_id=run_id, token_count=token_count)
        finally:
            # If we exit before the polling loop observed terminal status —
            # via raised exception, outer cancellation, or polling-exception
            # early return — the run is still alive on langgraph's side.
            # Cancel + verify so it doesn't orphan into the next challenge.
            if not terminal_observed and active.run_id is not None:
                try:
                    await self._cancel_and_verify_terminal(active)
                except Exception as exc:
                    log.warning("harness.escalation: orphan-run cancel failed: %s", exc)

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

    def _scan_workspace_for_output(self, workspace: Path, flag_pattern: re.Pattern[str]) -> str:
        """Scan workspace files for flag patterns recursively.

        ``flag_pattern`` comes from ``Challenge.flag_pattern`` so the scan and
        the provider's evaluation agree on what counts as a flag.

        The Docker sandbox creates files as root, so OSError (permission
        denied) is caught and silently skipped.
        """
        texts: list[str] = []
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
            except (OSError, UnicodeDecodeError) as exc:
                log.debug("Skipping unscannable file %s: %s", f, exc)

        return "\n\n".join(texts)
