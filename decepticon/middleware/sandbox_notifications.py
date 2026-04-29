"""Push background-job completion notices into the agent message stream.

When a tmux session's background command finishes, prepend a HumanMessage
with a <system-reminder> tag describing the completion. Anthropic models
recognize this tag as a runtime signal (the same pattern Claude Code uses)
without treating it as a real user turn.

Hook: before_model — runs every turn, so the agent learns about completions
on its very next inference even if it didn't poll bash_output.
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from decepticon.backends.docker_sandbox import DockerSandbox


class SandboxNotificationMiddleware(AgentMiddleware):
    """Emit one HumanMessage per turn aggregating new background completions."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        super().__init__()
        self._sandbox = sandbox
        self._notified: set[str] = set()

    def before_model(self, state, runtime):  # type: ignore[override]
        # Refresh status of still-running jobs we know about.
        for job in list(self._sandbox._jobs.all_jobs()):
            if job.status == "running":
                self._sandbox.poll_completion(job.session)

        new = [j for j in self._sandbox._jobs.pending_completions()
               if j.session not in self._notified]
        if not new:
            return None

        lines = ["<system-reminder>", "Background sandbox session updates:"]
        for job in new:
            lines.append(
                f"- {job.session}: completed exit {job.exit_code} "
                f"({job.elapsed:.0f}s) — command={job.command[:80]}"
            )
            self._notified.add(job.session)
        lines.append("Use bash_output(session) to retrieve full results.")
        lines.append("</system-reminder>")

        return {"messages": [HumanMessage(content="\n".join(lines))]}
