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
``NodeKind.FINDING`` node in the knowledge graph. The match is an exact
name set (:data:`_FINDING_TOOLS`) — substring matching on ``"finding"``
also caught readers and notifiers, making every finding event a false
positive.

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
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from typing_extensions import override

from decepticon.runtime.event_log import EventLog, EventType
from decepticon.telemetry.sink import (
    get_sink,
    reset_current_session,
    session_id_for,
    set_current_session,
)

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


# Tools that actually MATERIALIZE a finding. An exact set, not a substring
# match: "finding" in the name caught `read_shared_findings` and
# `broadcast_finding` — a reader and a notifier — so every finding event ever
# recorded in production was a false positive. New finding-emitting tools go
# here explicitly.
_FINDING_TOOLS = frozenset({"validate_finding"})


def _is_finding_tool(tool_name: str) -> bool:
    """True only for tools that create a ``NodeKind.FINDING`` node."""
    return tool_name.lower() in _FINDING_TOOLS


def _content_length(content: Any) -> int:
    """Length of a tool message's textual content without copying the blob."""
    if isinstance(content, str):
        return len(content)
    return len(str(content))


_TRAJ_TEXT_CAP = 12000


def _msg_text(content: Any) -> str:
    """Flatten a message's content (str or content-block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", "")))
        return " ".join(p for p in parts if p)
    return str(content) if content is not None else ""


# Harness-injected blocks that ride along inside a human message (background-job
# notices, hook output). They are machine-generated, not what the user typed, so
# they are stripped before the human turn is captured — otherwise ~1 in 4
# "user prompts" in the corpus is a system notice.
_SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _last_human_text(messages: Any) -> str:
    """The most recent human-message text — the objective/instruction context."""
    for msg in reversed(list(messages or [])):
        if getattr(msg, "type", "") == "human":
            return _msg_text(getattr(msg, "content", ""))
    return ""


def _user_text(messages: Any) -> str:
    """The human turn with harness-injected blocks removed.

    What remains is what the operator (or, for a subagent, the orchestrator)
    actually wrote — the prompt-pattern signal the corpus exists to capture.
    """
    return _SYSTEM_REMINDER.sub("", _last_human_text(messages)).strip()


def _ai_message(response: Any) -> Any:
    """The ``AIMessage`` inside a model-call result.

    ``wrap_model_call``'s handler returns a ``ModelResponse`` dataclass wrapping
    ``result: list[BaseMessage]`` — not the message itself. (Middleware may also
    return a bare ``AIMessage``, or an ``ExtendedModelResponse`` wrapping a
    ``ModelResponse``.) Reading ``.content`` / ``.usage_metadata`` /
    ``.response_metadata`` straight off the wrapper silently yielded nothing,
    which is the single root cause of three fields shipping empty in production:
    the agent's reasoning, the token counts, and the stop reason.
    """
    inner = getattr(response, "model_response", None)  # ExtendedModelResponse
    if inner is not None:
        response = inner
    result = getattr(response, "result", None)  # ModelResponse
    if isinstance(result, list):
        for msg in reversed(result):
            if getattr(msg, "type", "") == "ai":
                return msg
        return result[-1] if result else None
    return response  # already an AIMessage (the simplified middleware return)


def _reasoning_text(response: Any) -> str:
    """The model's chain-of-thought, wherever the provider parked it.

    Reasoning never arrives as plain ``text``: Anthropic extended thinking (on by
    default, see ``config/claude_code_handler.py``) returns ``thinking`` content
    blocks, LangChain's standard shape uses ``reasoning`` blocks, and
    OpenAI-compatible proxies (LiteLLM, DeepSeek) put it in
    ``additional_kwargs["reasoning_content"]``. Reading only ``text`` — as this
    middleware used to — captured none of it.
    """
    parts: list[str] = []
    kwargs = getattr(response, "additional_kwargs", None)
    if isinstance(kwargs, dict):
        raw = kwargs.get("reasoning_content")
        if isinstance(raw, str) and raw:
            parts.append(raw)
    content = getattr(response, "content", None)
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            for key in ("thinking", "reasoning"):
                raw = block.get(key)
                if isinstance(raw, str) and raw:
                    parts.append(raw)
    return "\n".join(parts)


def _model_name(request: Any) -> str:
    """Model id off the bound chat model.

    ``ChatOpenAI`` (every model in this stack routes through it via LiteLLM)
    exposes ``model_name``; ``name`` is the LangChain-generic fallback. Reading
    only ``name`` yielded an empty string on every real call.
    """
    model = getattr(request, "model", None)
    if model is None:
        return ""
    return str(getattr(model, "model_name", "") or getattr(model, "name", "") or "")


def _session_id(engagement: str | None) -> str:
    """A stable per-engagement session id. Delegates to the telemetry canonical
    :func:`session_id_for` so the middleware, OPPLAN, and finding tools all hash
    the engagement name identically (the grouping key must agree everywhere)."""
    return session_id_for(engagement)


def _roe_literal_targets(workspace: str) -> list[str]:
    """Literal in-scope hosts/IPs from ``<workspace>/plan/roe.json``.

    These are the engagement's actual authorized targets — ground truth that the
    research masker masks with certainty, covering identifiers the generic PII
    detectors miss (bare hostnames, NetBIOS names). CIDRs and domain globs are
    skipped (the detectors handle the concrete hosts under them).
    """
    import json
    from pathlib import Path

    from decepticon_core.types.roe import MachineEnforcement

    try:
        data = json.loads((Path(workspace) / "plan" / "roe.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    block = data.get("machine_enforcement") if isinstance(data, dict) else None
    rules = MachineEnforcement.from_dict(block)
    return [r.pattern for r in rules.in_scope if r.resolved_kind() in ("ip", "host")]


# Identity fields the operator DECLARES when the RoE is written — the
# roe-template skill interviews for each of them ("Client organization" is
# question 2). Nothing here is guessed: an absent field masks nothing.
_ROE_IDENTITY_FIELDS = ("client", "engagement_name", "engagement_slug", "authorized_by")


def _engagement_identity_terms(workspace: str) -> list[str]:
    """Who was tested, as declared by the engagement itself.

    No detector can find this. A client name is not shaped like a hostname, so
    regex cannot; a PII model scores F1 ~0.5 on names cross-domain, degrades
    further the further text sits from its training distribution, and would have
    to run on every trajectory step. The engagement, meanwhile, simply knows —
    the RoE interview asks for the client organization outright.

    Measured in the live corpus, these leaked verbatim: ``Workspace:
    /workspace/<client>-new`` inside prompts, and the authorizer's name.

    Only declared values are used, plus the workspace directory (which is the
    engagement slug on disk). Terms under 4 characters are skipped because a
    2-3 character string matches everywhere — there is no word list.
    """
    import json
    from pathlib import Path

    ws = Path(workspace)
    terms: list[str] = [ws.name]
    try:
        data = json.loads((ws / "plan" / "roe.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict):
        terms.extend(
            value for key in _ROE_IDENTITY_FIELDS if isinstance(value := data.get(key), str)
        )
    return [t for t in {t.strip() for t in terms} if len(t) >= 4]


class EventLogMiddleware(AgentMiddleware):
    """Emit compact engagement events to ``events.jsonl`` as the agent runs.

    Constructible with no arguments; everything is resolved per-call from
    ``request.state`` (keys ``engagement_name`` / ``workspace_path``) with
    env (``DECEPTICON_ENGAGEMENT_ID`` / ``DECEPTICON_WORKSPACE_PATH``) and
    hard-coded default fallbacks. Place anywhere in the stack — it only
    observes, never mutates, the request or response.
    """

    def __init__(self, role: str | None = None) -> None:
        super().__init__()
        # The agent this middleware was built for. ``build_middleware`` knows the
        # role; the runtime object does NOT carry an ``agent_name``, so without
        # this every event shipped with a null agent and per-specialist analysis
        # was impossible.
        self._role = role or None
        # Cache one EventLog per (workspace_root, engagement_id) so we don't
        # rebuild (and re-mkdir) on every model/tool call.
        self._logs: dict[tuple[str, str], EventLog] = {}
        # Consent-gated maintainer telemetry. Shared no-op sink when disabled
        # (the default), so this adds zero behavior unless the user opts in.
        self._telemetry = get_sink()
        # Workspaces whose RoE targets have already been fed to the masker.
        self._roe_seen: set[str] = set()
        # Last human-input hash per session, so the objective that repeats on
        # every model call inside this agent's loop is emitted once. The step
        # counter itself lives on the sink — it must be shared across agents.
        self._last_prompt: dict[str, str] = {}

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
        agent_name = self._role or ""
        if not agent_name:
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                agent_name = getattr(runtime, "agent_name", "") or ""
        return str(workspace), str(engagement), (agent_name or None)

    def _context(self, request: Any) -> tuple[EventLog | None, str | None, str]:
        """Resolve the EventLog, agent name, and per-engagement session id.

        ``session_id`` is hashed from the engagement so every telemetry event —
        not only research trajectory steps — carries the engagement grouping key
        (enables per-engagement analytics: kill-chain depth, tools/engagement).
        """
        workspace, engagement, agent = self._resolve_scope(request)
        sid = _session_id(engagement)
        key = (workspace, engagement)
        cached = self._logs.get(key)
        if cached is not None:
            return cached, agent, sid
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
            return None, agent, sid
        self._logs[key] = event_log
        return event_log, agent, sid

    def _safe_append(
        self,
        event_log: EventLog,
        event_type: EventType,
        payload: dict[str, Any],
        agent: str | None,
        session_id: str | None = None,
        *,
        telemetry: bool = True,
    ) -> None:
        """Append one event, swallowing any I/O failure with a warning.

        ``telemetry=False`` writes to disk only — used where a richer, correctly
        classified version of the same event is emitted elsewhere (findings are
        telemetered from the KG write path, which knows severity/CWE/MITRE).
        """
        try:
            event_log.append(event_type, payload, agent=agent)
        except Exception:  # noqa: BLE001 — logging must never break the run
            log.warning(
                "EventLogMiddleware: failed to append %s event; continuing",
                getattr(event_type, "value", event_type),
                exc_info=True,
            )
        if not telemetry:
            return
        # Mirror the same redacted event to the consent-gated telemetry sink.
        # `record` is itself fail-closed and never raises, so disk logging and
        # telemetry stay independent — one failing never affects the other.
        self._telemetry.record(
            getattr(event_type, "value", str(event_type)), payload, agent, session_id=session_id
        )

    # ── payload builders ──────────────────────────────────────────────────

    def _emit_llm_call(self, request: Any) -> None:
        event_log, agent, sid = self._context(request)
        if event_log is None:
            return
        messages = getattr(request, "messages", None) or []
        model_name = _model_name(request)
        payload: dict[str, Any] = {"messages": len(messages)}
        if model_name:
            payload["model"] = model_name
        self._safe_append(event_log, EventType.LLM_CALL, payload, agent, sid)

    def _emit_llm_response(self, request: Any, response: Any) -> None:
        event_log, agent, sid = self._context(request)
        if event_log is None:
            return
        payload: dict[str, Any] = {}
        message = _ai_message(response)
        usage = getattr(message, "usage_metadata", None) or {}
        if isinstance(usage, dict) and usage:
            payload["usage"] = usage
        metadata = getattr(message, "response_metadata", None) or {}
        if isinstance(metadata, dict):
            stop = metadata.get("finish_reason") or metadata.get("stop_reason")
            if stop:
                payload["stop"] = stop
        self._safe_append(event_log, EventType.LLM_RESPONSE, payload, agent, sid)

    def _emit_tool_call(self, request: Any) -> None:
        event_log, agent, sid = self._context(request)
        if event_log is None:
            return
        tool = getattr(request, "tool", None)
        tool_name = getattr(tool, "name", "") if tool else ""
        args = getattr(request, "tool_call_args", None) or {}
        payload = {"tool": tool_name, "args": _redact_args(args)}
        self._safe_append(event_log, EventType.TOOL_CALL, payload, agent, sid)

    def _emit_tool_result(self, request: Any, response: Any) -> None:
        event_log, agent, sid = self._context(request)
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
            self._safe_append(event_log, EventType.TOOL_RESULT, payload, agent, sid)
            # Emit the finding only after a *successful* finding-tool result, so
            # a failed validate_finding (status='error') never births a phantom
            # finding.created. Order stays tool.call -> tool.result -> finding.
            if status not in {"error"} and _is_finding_tool(tool_name):
                # Disk only: the telemetry copy is emitted by the KG write path
                # with the real severity/CWE/MITRE, so mirroring the bare
                # tool-name version here would double-count every finding.
                self._safe_append(
                    event_log,
                    EventType.FINDING_CREATED,
                    {"tool": tool_name},
                    agent,
                    sid,
                    telemetry=False,
                )
        else:
            # A Command (graph control-flow) carries no tool output to size, and
            # is not a tool *result*, so it never emits a finding.
            payload = {"tool": tool_name, "status": "command"}
            self._safe_append(event_log, EventType.TOOL_RESULT, payload, agent, sid)

    # ── research trajectory capture (reasoning corpus) ────────────────────
    # Only runs under research consent. Emits the raw prompt / agent reasoning /
    # action / observation to the telemetry sink, which MASKS target identifiers
    # before anything leaves the machine. No-op (and no extraction cost) otherwise.

    def _ensure_roe_known(self, workspace: str) -> None:
        """Once per workspace, feed the masker the RoE in-scope literal targets."""
        if workspace in self._roe_seen:
            return
        self._roe_seen.add(workspace)
        try:
            targets = _roe_literal_targets(workspace)
        except Exception:  # noqa: BLE001 — never break the run on a bad RoE file
            targets = []
        if targets:
            self._telemetry.add_known_targets(targets)
        # Client / engagement identity. Separate placeholder type because it is a
        # different disclosure: <HOST_1> is a machine, <ORG_1> is who was tested.
        try:
            identities = _engagement_identity_terms(workspace)
        except Exception:  # noqa: BLE001 — never break the run on a bad RoE file
            identities = []
        if identities:
            self._telemetry.add_known_targets(identities, "ORG")

    def _next_step(self, session_id: str) -> int:
        return self._telemetry.next_step(session_id)

    def _session_of(self, request: Any) -> str:
        _workspace, engagement, _agent = self._resolve_scope(request)
        return _session_id(engagement)

    def _emit_trajectory_model(self, request: Any, response: Any) -> None:
        if not self._telemetry.research:
            return
        try:
            import hashlib

            workspace, engagement, agent = self._resolve_scope(request)
            self._ensure_roe_known(workspace)
            sid = _session_id(engagement)
            model = _model_name(request)
            prompt = _user_text(getattr(request, "messages", None))[:_TRAJ_TEXT_CAP]
            # Chain-of-thought first, then the visible answer. A tool-calling turn
            # usually has empty visible content — the reasoning IS the turn.
            message = _ai_message(response)
            reasoning = "\n".join(
                part
                for part in (
                    _reasoning_text(message),
                    _msg_text(getattr(message, "content", "")),
                )
                if part
            )[:_TRAJ_TEXT_CAP]
            # Human input — emit only when it changes (the objective repeats every
            # model call inside the agent loop; we want one human turn, not N).
            if prompt:
                ph = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                if self._last_prompt.get(sid) != ph:
                    self._last_prompt[sid] = ph
                    self._telemetry.record_step(
                        {
                            "role": "human",
                            "session_id": sid,
                            "step": self._next_step(sid),
                            "text": prompt,
                        },
                        agent,
                        model=model,
                    )
            # Agent output — the reasoning / chain-of-thought.
            if reasoning:
                self._telemetry.record_step(
                    {
                        "role": "agent",
                        "session_id": sid,
                        "step": self._next_step(sid),
                        "text": reasoning,
                    },
                    agent,
                    model=model,
                )
        except Exception:  # noqa: BLE001 — telemetry must never break the run
            log.debug("trajectory model capture failed", exc_info=True)

    def _emit_trajectory_tool(self, request: Any, response: Any) -> None:
        if not self._telemetry.research:
            return
        try:
            import json

            workspace, engagement, agent = self._resolve_scope(request)
            self._ensure_roe_known(workspace)
            sid = _session_id(engagement)
            tool = getattr(getattr(request, "tool", None), "name", "") or ""
            args = getattr(request, "tool_call_args", None) or {}
            try:
                args_text = json.dumps(args, default=str)[:_TRAJ_TEXT_CAP]
            except (TypeError, ValueError):
                args_text = str(args)[:_TRAJ_TEXT_CAP]
            observation = ""
            if isinstance(response, ToolMessage):
                observation = _msg_text(getattr(response, "content", ""))[:_TRAJ_TEXT_CAP]
            step: dict[str, Any] = {
                "role": "tool",
                "session_id": sid,
                "step": self._next_step(sid),
                "args_text": args_text,
                "observation": observation,
            }
            if tool:  # omit empty tool — the gateway rejects an empty slug
                step["tool"] = tool
            self._telemetry.record_step(step, agent)
        except Exception:  # noqa: BLE001 — telemetry must never break the run
            log.debug("trajectory tool capture failed", exc_info=True)

    # ── middleware hooks ──────────────────────────────────────────────────

    @override
    def wrap_model_call(self, request, handler):
        self._emit_llm_call(request)
        response = handler(request)
        self._emit_llm_response(request, response)
        self._emit_trajectory_model(request, response)
        return response

    @override
    async def awrap_model_call(self, request, handler):
        self._emit_llm_call(request)
        response = await handler(request)
        self._emit_llm_response(request, response)
        self._emit_trajectory_model(request, response)
        return response

    @override
    def wrap_tool_call(self, request, handler):
        self._emit_tool_call(request)
        # Bind the engagement for the duration of the tool call so a tool that
        # emits telemetry itself (the finding path) lands in the right session.
        token = set_current_session(self._session_of(request))
        try:
            response = handler(request)
        finally:
            reset_current_session(token)
        self._emit_tool_result(request, response)
        self._emit_trajectory_tool(request, response)
        return response

    @override
    async def awrap_tool_call(self, request, handler):
        self._emit_tool_call(request)
        token = set_current_session(self._session_of(request))
        try:
            response = await handler(request)
        finally:
            reset_current_session(token)
        self._emit_tool_result(request, response)
        self._emit_trajectory_tool(request, response)
        return response
