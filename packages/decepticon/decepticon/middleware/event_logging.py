"""EventLogMiddleware — persist engagement events to ``events.jsonl`` live.

``decepticon.runtime.event_log.EventLog`` is the append-only writer for an
engagement's ``events.jsonl``; until now nothing in the production agent
stack actually drove it. This middleware closes that gap: it observes every
model and tool round-trip and emits a compact event line per phase, so the
orchestrator / dashboard can reconstruct an engagement timeline from disk.

Design mirrors :class:`decepticon.runtime.recording.RecordingMiddleware`
(wraps BOTH model and tool calls) but writes *summaries*, never full
prompts or tool output:

* before a model call  → :attr:`EventType.LLM_CALL`     (message count, model)
* after a model call   → :attr:`EventType.LLM_RESPONSE` (token/stop info if cheap)
* before a tool call   → :attr:`EventType.TOOL_CALL`    (tool name + redacted args)
* after a tool call    → :attr:`EventType.TOOL_RESULT`  (status + output length)

When the tool being invoked is the finding-emitting tool, a
:attr:`EventType.FINDING_CREATED` event is appended alongside the
``TOOL_CALL``. The canonical finding tool is ``validate_finding``
(:mod:`decepticon.tools.research.tools` / ``poc.py``), which materializes a
``NodeKind.FINDING`` node in the knowledge graph. Rather than hardcode one
name, we match any tool whose name contains ``"finding"`` (case-insensitive)
so future finding tools are caught without touching this file.

The middleware is constructed with no required arguments — workspace and
engagement id are resolved from ``request.state`` (with env + default
fallback) at call time, exactly like ``EngagementContextMiddleware()`` and
``BudgetEnforcementMiddleware``. One :class:`EventLog` is built lazily per
``(workspace_root, engagement_id)`` and cached on the instance.

Logging must never break the agent: both ``EventLog`` construction and
``append`` are wrapped so an unwritable workspace degrades to a silent
no-op (mirrors how ``budget.py`` swallows provider errors).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from typing_extensions import override

from decepticon.runtime.event_log import EventLog, EventType
from decepticon.telemetry.sink import get_sink

log = logging.getLogger(__name__)

_DEFAULT_WORKSPACE = "/workspace"
_DEFAULT_ENGAGEMENT = "default-engagement"

_REDACTED = "***REDACTED***"

# Substrings that mark a kwarg as a likely secret — value never written verbatim.
_SENSITIVE_KEY_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "auth",
    "private_key",
)


def _summarize_value(value: Any) -> Any:
    """Describe a value's shape without ever persisting its contents.

    Scalars (bool/int/float/None) are timeline-useful flags (``is_input``,
    ``timeout``, …) and kept verbatim; everything else collapses to a
    type+size tag, so a secret carried *inside* a value (a ``sshpass -p …``
    command, an ``Authorization`` header, a cookie token, a proxy body) can
    never leak to ``events.jsonl``.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return f"<str:{len(value)}>"
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple)):
        return f"<list:{len(value)}>"
    if isinstance(value, dict):
        return f"<dict:{len(value)} keys>"
    return f"<{type(value).__name__}>"


def _redact_args(args: Any) -> dict[str, Any]:
    """Return a content-free, structural summary of tool args.

    Persists only the *shape* of each value, never raw string/bytes/collection
    contents, so secrets carried in non-secret-named fields cannot reach the
    event log. Sensitive-named keys are masked outright.
    """
    if not isinstance(args, dict):
        return {"_args": _summarize_value(args)}
    out: dict[str, Any] = {}
    for key, val in args.items():
        if any(hint in str(key).lower() for hint in _SENSITIVE_KEY_HINTS):
            out[str(key)] = _REDACTED
        else:
            out[str(key)] = _summarize_value(val)
    return out


def _is_finding_tool(tool_name: str) -> bool:
    """Heuristic: any tool whose name contains ``finding`` emits a finding.

    Pins ``validate_finding`` (the KG finding-node creator) while staying
    forward-compatible with future finding-emitting tools.
    """
    return "finding" in tool_name.lower()


def _content_length(content: Any) -> int:
    """Length of a tool message's textual content without copying the blob."""
    if isinstance(content, str):
        return len(content)
    return len(str(content))


class EventLogMiddleware(AgentMiddleware):
    """Emit compact engagement events to ``events.jsonl`` as the agent runs.

    Constructible with no arguments; everything is resolved per-call from
    ``request.state`` (keys ``engagement_name`` / ``workspace_path``) with
    env (``DECEPTICON_ENGAGEMENT_ID`` / ``DECEPTICON_WORKSPACE_PATH``) and
    hard-coded default fallbacks. Place anywhere in the stack — it only
    observes, never mutates, the request or response.
    """

    def __init__(self) -> None:
        super().__init__()
        # Cache one EventLog per (workspace_root, engagement_id) so we don't
        # rebuild (and re-mkdir) on every model/tool call.
        self._logs: dict[tuple[str, str], EventLog] = {}
        # Consent-gated maintainer telemetry. Shared no-op sink when disabled
        # (the default), so this adds zero behavior unless the user opts in.
        self._telemetry = get_sink()

    # ── scope + log resolution ────────────────────────────────────────────

    def _resolve_scope(self, request: Any) -> tuple[str, str, str | None]:
        """Return ``(workspace_root, engagement_id, agent_name_or_None)``."""
        state = getattr(request, "state", None) or {}
        get = state.get if hasattr(state, "get") else (lambda _k, _d=None: None)
        engagement = (
            get("engagement_name")
            or get("engagement_id")
            or os.environ.get("DECEPTICON_ENGAGEMENT_ID", "")
            or _DEFAULT_ENGAGEMENT
        )
        workspace = (
            get("workspace_path")
            or os.environ.get("DECEPTICON_WORKSPACE_PATH", "")
            or _DEFAULT_WORKSPACE
        )
        agent_name = ""
        runtime = getattr(request, "runtime", None)
        if runtime is not None:
            agent_name = getattr(runtime, "agent_name", "") or ""
        return str(workspace), str(engagement), (agent_name or None)

    def _context(self, request: Any) -> tuple[EventLog | None, str | None]:
        """Resolve (and lazily build/cache) the EventLog plus the agent name."""
        workspace, engagement, agent = self._resolve_scope(request)
        key = (workspace, engagement)
        cached = self._logs.get(key)
        if cached is not None:
            return cached, agent
        try:
            event_log = EventLog.for_workspace(workspace, engagement)
        except Exception:  # noqa: BLE001 — never break the agent on a bad path
            log.warning(
                "EventLogMiddleware: cannot open event log "
                "(workspace=%s engagement=%s); events disabled for this scope",
                workspace,
                engagement,
                exc_info=True,
            )
            return None, agent
        self._logs[key] = event_log
        return event_log, agent

    def _safe_append(
        self,
        event_log: EventLog,
        event_type: EventType,
        payload: dict[str, Any],
        agent: str | None,
    ) -> None:
        """Append one event, swallowing any I/O failure with a warning."""
        try:
            event_log.append(event_type, payload, agent=agent)
        except Exception:  # noqa: BLE001 — logging must never break the run
            log.warning(
                "EventLogMiddleware: failed to append %s event; continuing",
                getattr(event_type, "value", event_type),
                exc_info=True,
            )
        # Mirror the same redacted event to the consent-gated telemetry sink.
        # `record` is itself fail-closed and never raises, so disk logging and
        # telemetry stay independent — one failing never affects the other.
        self._telemetry.record(getattr(event_type, "value", str(event_type)), payload, agent)

    # ── payload builders ──────────────────────────────────────────────────

    def _emit_llm_call(self, request: Any) -> None:
        event_log, agent = self._context(request)
        if event_log is None:
            return
        messages = getattr(request, "messages", None) or []
        model_name = getattr(getattr(request, "model", None), "name", "") or ""
        payload: dict[str, Any] = {"messages": len(messages)}
        if model_name:
            payload["model"] = model_name
        self._safe_append(event_log, EventType.LLM_CALL, payload, agent)

    def _emit_llm_response(self, request: Any, response: Any) -> None:
        event_log, agent = self._context(request)
        if event_log is None:
            return
        payload: dict[str, Any] = {}
        usage = getattr(response, "usage_metadata", None) or {}
        if isinstance(usage, dict) and usage:
            payload["usage"] = usage
        metadata = getattr(response, "response_metadata", None) or {}
        if isinstance(metadata, dict):
            stop = metadata.get("finish_reason") or metadata.get("stop_reason")
            if stop:
                payload["stop"] = stop
        self._safe_append(event_log, EventType.LLM_RESPONSE, payload, agent)

    def _emit_tool_call(self, request: Any) -> None:
        event_log, agent = self._context(request)
        if event_log is None:
            return
        tool = getattr(request, "tool", None)
        tool_name = getattr(tool, "name", "") if tool else ""
        args = getattr(request, "tool_call_args", None) or {}
        payload = {"tool": tool_name, "args": _redact_args(args)}
        self._safe_append(event_log, EventType.TOOL_CALL, payload, agent)

    def _emit_tool_result(self, request: Any, response: Any) -> None:
        event_log, agent = self._context(request)
        if event_log is None:
            return
        tool = getattr(request, "tool", None)
        tool_name = getattr(tool, "name", "") if tool else ""
        if isinstance(response, ToolMessage):
            status = getattr(response, "status", "") or ""
            payload: dict[str, Any] = {
                "tool": tool_name,
                "status": status,
                "output_chars": _content_length(getattr(response, "content", "")),
            }
            self._safe_append(event_log, EventType.TOOL_RESULT, payload, agent)
            # Emit the finding only after a *successful* finding-tool result, so
            # a failed validate_finding (status='error') never births a phantom
            # finding.created. Order stays tool.call -> tool.result -> finding.
            if status not in {"error"} and _is_finding_tool(tool_name):
                self._safe_append(event_log, EventType.FINDING_CREATED, {"tool": tool_name}, agent)
        else:
            # A Command (graph control-flow) carries no tool output to size, and
            # is not a tool *result*, so it never emits a finding.
            payload = {"tool": tool_name, "status": "command"}
            self._safe_append(event_log, EventType.TOOL_RESULT, payload, agent)

    # ── middleware hooks ──────────────────────────────────────────────────

    @override
    def wrap_model_call(self, request, handler):
        self._emit_llm_call(request)
        response = handler(request)
        self._emit_llm_response(request, response)
        return response

    @override
    async def awrap_model_call(self, request, handler):
        self._emit_llm_call(request)
        response = await handler(request)
        self._emit_llm_response(request, response)
        return response

    @override
    def wrap_tool_call(self, request, handler):
        self._emit_tool_call(request)
        response = handler(request)
        self._emit_tool_result(request, response)
        return response

    @override
    async def awrap_tool_call(self, request, handler):
        self._emit_tool_call(request)
        response = await handler(request)
        self._emit_tool_result(request, response)
        return response
