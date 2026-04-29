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
import threading

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from decepticon.backends.docker_sandbox import DockerSandbox


class SandboxNotificationMiddleware(AgentMiddleware):
    """Emit one HumanMessage per turn aggregating new background completions."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        super().__init__()
        self._sandbox = sandbox
        self._notified: set[str] = set()
        self._lock = threading.Lock()

    def _build_message(self) -> dict | None:
        """Build the system-reminder message dict, or None if nothing new."""
        with self._lock:
            new = [
                j
                for j in self._sandbox._jobs.pending_completions()
                if j.session not in self._notified
            ]
            if not new:
                return None
            for job in new:
                self._notified.add(job.session)

        lines = ["<system-reminder>", "Background sandbox session updates:"]
        for job in new:
            lines.append(
                f"- {job.session}: completed exit {job.exit_code} "
                f"({job.elapsed:.0f}s) — command={job.command[:80]}"
            )
        lines.append("Use bash_output(session) to retrieve full results.")
        lines.append("</system-reminder>")
        return {"messages": [HumanMessage(content="\n".join(lines))]}

    def before_model(self, state, runtime):  # type: ignore[override]
        # Refresh status of still-running jobs (sync subprocess calls).
        for job in list(self._sandbox._jobs.all_jobs()):
            if job.status == "running":
                self._sandbox.poll_completion(job.session)
        return self._build_message()

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        # Async path: offload blocking subprocess polls to a thread so we
        # do not stall the LangGraph event loop.
        for job in list(self._sandbox._jobs.all_jobs()):
            if job.status == "running":
                await asyncio.to_thread(self._sandbox.poll_completion, job.session)
        return self._build_message()
