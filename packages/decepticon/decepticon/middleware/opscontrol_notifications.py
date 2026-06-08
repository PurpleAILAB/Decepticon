"""Push opscontrol workload state transitions into the agent message stream.

Mirror of :mod:`decepticon.middleware.notifications` (which handles bash
background-job completion) for the ADR-0006 opscontrol daemon. When a
workload the agent spawned with ``ops_start("ad")`` transitions to
``running`` (or ``stopped`` / ``unknown`` on failure), this middleware:

  1. Polls ``GET /v1/profiles`` once per turn via the daemon's
     Unix-domain socket bind-mount.
  2. Diffs the registry snapshot against the last-seen state per
     workload, dedup'd so a workload already announced as ``running``
     does not re-notify on every turn.
  3. Injects a ``HumanMessage`` tagged ``<system-reminder>`` carrying the
     transition summary, so the agent can react on its very next
     inference turn without calling ``ops_status``.

Hook: ``before_model`` — runs every turn, so completions land on the
very next inference even if the user did nothing between turns.

Design intent
-------------
The agent calls ``ops_start("ad")`` and IMMEDIATELY moves on. It does
NOT call ``ops_status`` in a polling loop — this middleware is the
delivery mechanism. The model is told (via the orchestrator prompt
``Section F``) to expect a system-reminder when the workload is
ready, and to delegate to the specialist on that turn.

Convergent industry pattern: Claude Code's ``Bash(run_in_background)``
→ background-completion notification, Decepticon's own
``SandboxNotificationMiddleware`` for tmux session completions, and the
LangChain ``async-deep-agents`` reference implementation all use this
shape. See docs/adr/0006 §6 for the full reference list.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage

from decepticon.tools.ops.client import (
    OpsControlClient,
    OpsControlError,
    OpsControlUnreachableError,
)

log = logging.getLogger(__name__)

# Workload state strings — must match the daemon's internal
# ``WorkloadState`` constants (clients/launcher/internal/opscontrol/backend.go).
STATE_RUNNING = "running"
STATE_STARTING = "starting"
STATE_STOPPED = "stopped"
STATE_UNKNOWN = "unknown"

# State transitions that warrant a notification. Starting → running is
# the load-bearing case (BHCE cold-start completion); → stopped / →
# unknown surface failure modes so the agent doesn't silently wait
# forever for a workload that crashed.
_NOTIFIABLE_TARGETS = (STATE_RUNNING, STATE_STOPPED, STATE_UNKNOWN)


# Per-turn system-prompt injection that codifies the ops_* tool
# contract. Mirrors how `EngagementContextMiddleware` carries
# `<ENGAGEMENT_CONTEXT>` and `LANGUAGE_POLICY` blocks — same shape,
# same delivery channel (request.override(system_message=...)).
#
# Why this lives in the middleware rather than the static system
# prompt: the auto-notification contract is what justifies "do not
# poll ops_status." Coupling the wording to the middleware that
# DELIVERS the notifications guarantees the two never drift — if the
# middleware is swapped out by a plugin the wording must come with it.
_OPS_POLICY_BLOCK = """
<OPSCONTROL_POLICY>
- `ops_start("<workload>")` returns immediately with `state: "starting"`.
  A `<system-reminder>` is auto-injected on a later turn:
  `● Workload 'ad': starting → running`. That reminder is the ready
  signal. Do NOT poll `ops_status` waiting for it.
- `→ stopped` / `→ unknown` in the reminder means spawn failed —
  block the dependent specialist objective.
- `ops_status` is a fallback (daemon reachability check, suspected
  lost notification, operator asking "what is up?"). Routine polling
  burns context.
</OPSCONTROL_POLICY>
""".strip()


class OpsControlNotificationMiddleware(AgentMiddleware):
    """Auto-deliver opscontrol workload state transitions to the agent."""

    def __init__(self, client: OpsControlClient | None = None) -> None:
        super().__init__()
        # Lazy construction — instantiating the client does not open a
        # socket connection, so this is cheap even when no daemon is
        # available (e.g. ``make dev`` / ``make smoke`` paths). Tests
        # may inject a stub client.
        self._client = client or OpsControlClient()
        # Per-workload last announced state. We notify only when the
        # incoming state differs AND is one of _NOTIFIABLE_TARGETS, so
        # the model sees one reminder per transition, not one per turn.
        self._last_state: dict[str, str] = {}
        self._lock = threading.Lock()

    def _snapshot(self) -> list[dict[str, Any]] | None:
        """Pull the current registry. None on any daemon-side error so
        the middleware degrades gracefully — a temporary daemon hiccup
        must not crash the agent's model step.
        """
        try:
            return self._client.list_profiles()
        except OpsControlUnreachableError:
            # Common in daemon-less stacks (make dev / make smoke); not
            # worth logging at WARN every turn.
            log.debug("opscontrol daemon unreachable; skipping notification poll")
            return None
        except OpsControlError as exc:
            log.warning("opscontrol /v1/profiles returned %d: %s", exc.status_code, exc.body)
            return None
        except Exception as exc:  # noqa: BLE001 — defensive
            log.warning("opscontrol notification poll failed: %s", exc)
            return None

    def _format_block(self, record: dict[str, Any], previous: str | None) -> str:
        workload = record.get("workload", "?")
        state = record.get("state", "?")
        engagement = record.get("engagement_id") or ""
        since = record.get("since") or ""
        prev = previous or "new"
        parts = [f"workload={workload!r}", f"state={prev}->{state}"]
        if engagement:
            parts.append(f"engagement={engagement}")
        if since:
            parts.append(f"since={since}")
        return "- " + " ".join(parts)

    def _build_message(self) -> dict | None:
        snapshot = self._snapshot()
        if not snapshot:
            return None

        blocks: list[str] = []
        with self._lock:
            for record in snapshot:
                workload = record.get("workload")
                state = record.get("state")
                if not workload or not state:
                    continue
                previous = self._last_state.get(workload)
                if state == previous:
                    continue
                if state not in _NOTIFIABLE_TARGETS:
                    # starting → starting / not yet entered a
                    # notifiable terminal state. Update the cache so a
                    # later transition includes the right "from" hint
                    # but emit nothing.
                    self._last_state[workload] = state
                    continue
                blocks.append(self._format_block(record, previous))
                self._last_state[workload] = state

        if not blocks:
            return None

        body = "\n".join(blocks)
        reminder = (
            "<system-reminder>\n"
            "Workload state transitions delivered by the opscontrol daemon. "
            "Authoritative — do not call ops_status to re-confirm:\n"
            f"{body}\n"
            "</system-reminder>"
        )
        # HumanMessage matches the existing SandboxNotificationMiddleware
        # convention and the Claude Code system-reminder shape (user-role
        # message wrapping a tagged block). Keeps the agent's
        # turn-taking transcript clean: assistant -> tool -> human
        # reminder -> assistant, never two consecutive assistant turns.
        return {"messages": [HumanMessage(content=reminder)]}

    def before_model(self, state, runtime):  # type: ignore[override]
        return self._build_message()

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        # The underlying httpx client is sync; this is a sub-millisecond
        # local UDS call so we don't wrap it in asyncio.to_thread for
        # latency reasons. Keep the async sibling so subclasses can
        # override with a true-async client if they wire one in.
        return self._build_message()

    def wrap_model_call(self, request, handler):  # type: ignore[override]
        return handler(self._inject(request))

    async def awrap_model_call(self, request, handler):  # type: ignore[override]
        return await handler(self._inject(request))

    def _inject(self, request):
        """Append the OPSCONTROL_POLICY block to the request's system
        message. Mirrors EngagementContextMiddleware's pattern so the
        two cooperate cleanly (each appends to whatever the previous
        middleware produced).
        """
        injection = _OPS_POLICY_BLOCK
        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": "\n\n" + injection},
            ]
        else:
            new_content = [{"type": "text", "text": injection}]
        new_system = SystemMessage(content=cast("list[str | dict[str, str]]", new_content))
        return request.override(system_message=new_system)
