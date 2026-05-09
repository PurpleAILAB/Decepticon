"""Push background-job completion notices into the agent message stream.

When a tmux session's background command finishes, prepend a HumanMessage
with a <system-reminder> tag describing the completion. Anthropic models
recognize this tag as a runtime signal (the same pattern Claude Code uses)
without treating it as a real user turn.

Hook: before_model — runs every turn, so the agent learns about completions
on its very next inference even if it didn't poll bash_output.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from decepticon.backends.docker_sandbox import DockerSandbox

log = logging.getLogger(__name__)

# Cap on how many job keys we track to avoid unbounded memory growth in
# long-lived agent sessions. We hold an ``OrderedDict`` keyed by job.key
# and evict in FIFO order — duplicate notifications for evicted keys are
# acceptable (the alternative is uncapped growth).
_NOTIFIED_KEYS_MAX = 4096


class SandboxNotificationMiddleware(AgentMiddleware):
    """Emit one HumanMessage per turn aggregating new background completions."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        super().__init__()
        self._sandbox = sandbox
        # OrderedDict-as-set so we can both check membership and evict in
        # insertion order. Values are unused; we keep ``True`` to make the
        # intent explicit at call sites.
        self._notified: OrderedDict[str, bool] = OrderedDict()
        self._lock = threading.Lock()

    def _jobs_view(self):
        """Defensive accessor for the sandbox's job registry.

        ``DockerSandbox`` exposes ``_jobs`` as an internal attribute. Going
        through ``getattr`` lets us survive a backend that has not yet
        attached the registry (e.g. a partially constructed sandbox in a
        test fixture) without crashing the middleware.
        """
        return getattr(self._sandbox, "_jobs", None)

    def _record_notified(self, keys) -> None:
        """Insert keys into the bounded notified-set, evicting oldest first."""
        for key in keys:
            self._notified[key] = True
        while len(self._notified) > _NOTIFIED_KEYS_MAX:
            self._notified.popitem(last=False)

    def _build_message(self) -> dict | None:
        """Build the system-reminder message dict, or None if nothing new."""
        jobs = self._jobs_view()
        if jobs is None:
            return None
        try:
            pending = list(jobs.pending_completions())
        except Exception as e:  # noqa: BLE001 — best-effort middleware
            log.warning("Failed to read pending completions from sandbox: %s", e)
            return None

        with self._lock:
            new = [j for j in pending if j.key not in self._notified]
            if not new:
                return None
            self._record_notified(j.key for j in new)

        lines = ["<system-reminder>", "Background sandbox session updates:"]
        for job in new:
            command = (job.command or "")[:80]
            lines.append(
                f"- {job.session}: completed exit {job.exit_code} "
                f"({job.elapsed:.0f}s) — command={command}"
            )
        lines.append("Use bash_output(session) to retrieve full results.")
        lines.append("</system-reminder>")
        return {"messages": [HumanMessage(content="\n".join(lines))]}

    def _refresh_running_jobs(self) -> None:
        """Sync poll for still-running jobs; swallow per-job subprocess errors."""
        jobs = self._jobs_view()
        if jobs is None:
            return
        try:
            running = [j for j in jobs.all_jobs() if j.status == "running"]
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to enumerate sandbox jobs: %s", e)
            return
        for job in running:
            try:
                self._sandbox.poll_completion(job.session, workspace_path=job.workspace_path)
            except Exception as e:  # noqa: BLE001
                log.warning("poll_completion failed for session=%s: %s", job.session, e)

    async def _arefresh_running_jobs(self) -> None:
        """Async sibling of ``_refresh_running_jobs`` — same error semantics."""
        jobs = self._jobs_view()
        if jobs is None:
            return
        try:
            running = [j for j in jobs.all_jobs() if j.status == "running"]
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to enumerate sandbox jobs: %s", e)
            return
        for job in running:
            try:
                await asyncio.to_thread(
                    self._sandbox.poll_completion,
                    job.session,
                    workspace_path=job.workspace_path,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("poll_completion failed for session=%s: %s", job.session, e)

    def before_model(self, state, runtime):  # type: ignore[override]
        self._refresh_running_jobs()
        return self._build_message()

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        await self._arefresh_running_jobs()
        return self._build_message()
