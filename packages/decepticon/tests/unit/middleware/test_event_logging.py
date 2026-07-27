"""Tests for decepticon.middleware.event_logging."""

from __future__ import annotations

import asyncio
from pathlib import Path

from langchain_core.messages import ToolMessage

from decepticon.middleware.event_logging import (
    EventLogMiddleware,
    _redact_args,
    _summarize_value,
)
from decepticon.runtime.event_log import EventType, read_events

# ── fakes mirroring the request/handler shapes used by other middleware tests ──


class _Model:
    def __init__(self, name: str) -> None:
        self.name = name


class _Runtime:
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name


class _ModelRequest:
    def __init__(self, workspace: Path, engagement: str, *, messages, model, agent):
        self.state = {"workspace_path": str(workspace), "engagement_name": engagement}
        self.runtime = _Runtime(agent)
        self.messages = messages
        self.model = _Model(model)


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _ToolRequest:
    def __init__(self, workspace: Path, engagement: str, *, tool, args, agent):
        self.state = {"workspace_path": str(workspace), "engagement_name": engagement}
        self.runtime = _Runtime(agent)
        self.tool = _Tool(tool)
        self.tool_call_args = args


def _events_path(workspace: Path, engagement: str) -> Path:
    return workspace / "events.jsonl"


# ── helpers ────────────────────────────────────────────────────────────────


def test_summarize_value_describes_shape_without_contents():
    assert _summarize_value("hunter2") == "<str:7>"
    assert _summarize_value(b"abcd") == "<bytes:4>"
    assert _summarize_value([1, 2, 3]) == "<list:3>"
    assert _summarize_value((1, 2)) == "<list:2>"
    assert _summarize_value({"a": 1, "b": 2}) == "<dict:2 keys>"
    # Scalars are timeline-useful flags and kept verbatim.
    assert _summarize_value(True) is True
    assert _summarize_value(30) == 30
    assert _summarize_value(None) is None
    assert _summarize_value(object()) == "<object>"


def test_redact_args_never_persists_value_contents():
    command = "sshpass -p hunter2\n"
    out = _redact_args(
        {
            "command": command,
            "is_input": True,
            "timeout": 30,
            "password": "hunter2",
        }
    )
    # B2: a secret carried in a non-secret-named field leaks only its shape.
    assert out["command"] == "<str:%d>" % len(command)
    assert "hunter2" not in out["command"]
    # Scalar flags stay verbatim — useful for the timeline, not a leak risk.
    assert out["is_input"] is True
    assert out["timeout"] == 30
    # Sensitive-named keys are masked outright.
    assert out["password"] == "***REDACTED***"


# ── model round-trip ─────────────────────────────────────────────────────────


def test_model_call_writes_llm_call_then_response_pair(tmp_path: Path):
    mw = EventLogMiddleware()

    class _Resp:
        usage_metadata = {"input_tokens": 5, "output_tokens": 2}
        response_metadata = {"finish_reason": "stop"}

    resp = _Resp()
    req = _ModelRequest(
        tmp_path, "eng-1", messages=["a", "b", "c"], model="claude-opus", agent="recon"
    )

    out = mw.wrap_model_call(req, lambda _r: resp)
    assert out is resp

    events = list(read_events(_events_path(tmp_path, "eng-1")))
    assert [e.type for e in events] == [
        EventType.LLM_CALL.value,
        EventType.LLM_RESPONSE.value,
    ]
    assert events[0].payload == {"messages": 3, "model": "claude-opus"}
    assert events[0].agent == "recon"
    assert events[1].payload["usage"] == {"input_tokens": 5, "output_tokens": 2}
    assert events[1].payload["stop"] == "stop"


# ── tool round-trip ──────────────────────────────────────────────────────────


def test_tool_call_writes_call_then_result_pair(tmp_path: Path):
    mw = EventLogMiddleware()
    req = _ToolRequest(
        tmp_path, "eng-2", tool="bash", args={"command": "id", "token": "s3cr3t"}, agent="recon"
    )
    result = ToolMessage(content="uid=0(root)", tool_call_id="t1", name="bash", status="success")

    out = mw.wrap_tool_call(req, lambda _r: result)
    assert out is result

    events = list(read_events(_events_path(tmp_path, "eng-2")))
    assert [e.type for e in events] == [
        EventType.TOOL_CALL.value,
        EventType.TOOL_RESULT.value,
    ]
    assert events[0].payload["tool"] == "bash"
    assert events[0].payload["args"]["command"] == "<str:2>"
    assert events[0].payload["args"]["token"] == "***REDACTED***"
    assert events[1].payload["status"] == "success"
    assert events[1].payload["output_chars"] == len("uid=0(root)")


def test_finding_tool_writes_finding_after_successful_result(tmp_path: Path):
    mw = EventLogMiddleware()
    req = _ToolRequest(
        tmp_path, "eng-3", tool="validate_finding", args={"vuln_id": "V-1"}, agent="exploit"
    )
    result = ToolMessage(content="{}", tool_call_id="t2", name="validate_finding", status="success")

    mw.wrap_tool_call(req, lambda _r: result)

    events = list(read_events(_events_path(tmp_path, "eng-3")))
    # B3: order is tool.call -> tool.result -> finding.created (finding emitted
    # only after a successful result, never before the tool runs).
    assert [e.type for e in events] == [
        EventType.TOOL_CALL.value,
        EventType.TOOL_RESULT.value,
        EventType.FINDING_CREATED.value,
    ]
    assert events[2].payload == {"tool": "validate_finding"}


def test_failed_finding_tool_does_not_write_finding_created(tmp_path: Path):
    mw = EventLogMiddleware()
    req = _ToolRequest(
        tmp_path, "eng-3b", tool="validate_finding", args={"vuln_id": "V-1"}, agent="exploit"
    )
    # A failed validate_finding returns an error ToolMessage — no phantom finding.
    result = ToolMessage(
        content="invalid", tool_call_id="t2b", name="validate_finding", status="error"
    )

    mw.wrap_tool_call(req, lambda _r: result)

    events = list(read_events(_events_path(tmp_path, "eng-3b")))
    assert [e.type for e in events] == [
        EventType.TOOL_CALL.value,
        EventType.TOOL_RESULT.value,
    ]
    assert EventType.FINDING_CREATED.value not in [e.type for e in events]


def test_finding_tool_command_result_does_not_write_finding_created(tmp_path: Path):
    mw = EventLogMiddleware()
    req = _ToolRequest(
        tmp_path, "eng-3c", tool="validate_finding", args={"vuln_id": "V-1"}, agent="exploit"
    )
    # A Command (graph control-flow) result is not a finding-bearing ToolMessage.
    command_result = object()

    mw.wrap_tool_call(req, lambda _r: command_result)

    types = [e.type for e in read_events(_events_path(tmp_path, "eng-3c"))]
    assert types == [EventType.TOOL_CALL.value, EventType.TOOL_RESULT.value]
    assert EventType.FINDING_CREATED.value not in types


def test_non_finding_tool_does_not_write_finding_created(tmp_path: Path):
    mw = EventLogMiddleware()
    req = _ToolRequest(tmp_path, "eng-4", tool="bash", args={}, agent="recon")
    result = ToolMessage(content="ok", tool_call_id="t3", name="bash", status="success")

    mw.wrap_tool_call(req, lambda _r: result)

    types = [e.type for e in read_events(_events_path(tmp_path, "eng-4"))]
    assert EventType.FINDING_CREATED.value not in types


# ── failure is swallowed ─────────────────────────────────────────────────────


def test_append_failure_is_swallowed(tmp_path: Path):
    # Pre-create events.jsonl as a *directory* so EventLog.append's open()
    # fails. Construction (which only mkdir's the parent) still succeeds.
    bad = _events_path(tmp_path, "eng-5")
    bad.mkdir(parents=True)

    mw = EventLogMiddleware()
    req = _ToolRequest(tmp_path, "eng-5", tool="bash", args={}, agent="recon")
    sentinel = ToolMessage(content="ok", tool_call_id="t4", name="bash", status="success")

    # Must not raise, and must still return the handler's response.
    out = mw.wrap_tool_call(req, lambda _r: sentinel)
    assert out is sentinel


# ── caching + async parity ───────────────────────────────────────────────────


def test_event_log_cached_per_scope(tmp_path: Path):
    mw = EventLogMiddleware()
    req = _ModelRequest(tmp_path, "eng-6", messages=[], model="m", agent="a")
    mw.wrap_model_call(req, lambda _r: type("R", (), {})())
    first = mw._logs[(str(tmp_path), "eng-6")]
    mw.wrap_model_call(req, lambda _r: type("R", (), {})())
    assert mw._logs[(str(tmp_path), "eng-6")] is first
    assert len(mw._logs) == 1


def test_async_hooks_write_events(tmp_path: Path):
    mw = EventLogMiddleware()

    async def _model_handler(_r):
        return type("R", (), {"usage_metadata": {}, "response_metadata": {}})()

    async def _tool_handler(_r):
        return ToolMessage(content="x", tool_call_id="t5", name="bash", status="success")

    async def _drive():
        mreq = _ModelRequest(tmp_path, "eng-7", messages=["m"], model="m", agent="a")
        await mw.awrap_model_call(mreq, _model_handler)
        treq = _ToolRequest(tmp_path, "eng-7", tool="bash", args={}, agent="a")
        await mw.awrap_tool_call(treq, _tool_handler)

    asyncio.run(_drive())

    types = [e.type for e in read_events(_events_path(tmp_path, "eng-7"))]
    assert types == [
        EventType.LLM_CALL.value,
        EventType.LLM_RESPONSE.value,
        EventType.TOOL_CALL.value,
        EventType.TOOL_RESULT.value,
    ]


# ── reasoning / prompt capture (the research corpus' whole point) ─────────────


def test_reasoning_text_reads_thinking_and_reasoning_content():
    from decepticon.middleware.event_logging import _reasoning_text

    class _Resp:
        content = [
            {"type": "thinking", "thinking": "port 8080 is odd — probe it"},
            {"type": "text", "text": "Running nmap."},
        ]
        additional_kwargs = {"reasoning_content": "proxy-side CoT"}

    out = _reasoning_text(_Resp())
    assert "port 8080 is odd" in out  # Anthropic extended-thinking block
    assert "proxy-side CoT" in out  # LiteLLM / DeepSeek passthrough
    assert "Running nmap." not in out  # visible answer is not reasoning


def test_reasoning_survives_a_tool_calling_turn_with_no_visible_text():
    from decepticon.middleware.event_logging import _msg_text, _reasoning_text

    class _Resp:
        content = [{"type": "thinking", "thinking": "escalate via sudo -l"}]
        additional_kwargs: dict = {}

    # The visible content is empty — reading only `text` (the old behavior)
    # captured nothing at all for every tool-calling turn.
    assert _msg_text(_Resp.content).strip() == ""
    assert _reasoning_text(_Resp()) == "escalate via sudo -l"


def test_user_text_strips_harness_injected_reminders():
    from decepticon.middleware.event_logging import _user_text

    class _Msg:
        type = "human"
        content = (
            "<system-reminder>\nBackground sandbox sessions completed.\n</system-reminder>\n"
            "get me a shell on the DMZ box"
        )

    assert _user_text([_Msg()]) == "get me a shell on the DMZ box"


def test_agent_name_comes_from_the_role_not_the_runtime(tmp_path: Path):
    # The runtime object carries no agent_name in production, so the role passed
    # by build_middleware is the only reliable source.
    mw = EventLogMiddleware(role="recon")

    class _NoNameRuntime:
        pass

    req = _ToolRequest(tmp_path, "eng-role", tool="bash", args={}, agent="")
    req.runtime = _NoNameRuntime()
    mw.wrap_tool_call(req, lambda _r: ToolMessage(content="ok", tool_call_id="t", status="success"))

    events = list(read_events(_events_path(tmp_path, "eng-role")))
    assert events and all(e.agent == "recon" for e in events)


def test_reader_and_broadcast_tools_are_not_findings(tmp_path: Path):
    # Substring matching on "finding" made these two the ONLY finding events
    # ever recorded in production — both false positives.
    from decepticon.middleware.event_logging import _is_finding_tool

    assert _is_finding_tool("validate_finding")
    assert not _is_finding_tool("read_shared_findings")
    assert not _is_finding_tool("broadcast_finding")


# ── the real ModelResponse wrapper (root cause of three empty fields) ────────


def _model_response(message):
    """The exact shape `wrap_model_call`'s handler returns in production."""
    from langchain.agents.middleware.types import ModelResponse

    return ModelResponse(result=[message])


def test_ai_message_is_unwrapped_from_the_model_response_wrapper():
    from langchain_core.messages import AIMessage

    from decepticon.middleware.event_logging import _ai_message

    msg = AIMessage(content="hi")
    assert _ai_message(_model_response(msg)) is msg
    assert _ai_message(msg) is msg  # bare AIMessage return is also legal


def test_llm_response_records_tokens_through_the_wrapper(tmp_path: Path):
    # tokens shipped 0/91,983 in production: usage_metadata was read off the
    # ModelResponse wrapper, which has no such attribute.
    from langchain_core.messages import AIMessage

    mw = EventLogMiddleware(role="recon")
    msg = AIMessage(
        content="done",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        response_metadata={"finish_reason": "stop"},
    )
    req = _ModelRequest(tmp_path, "eng-tok", messages=["m"], model="m", agent="recon")
    mw.wrap_model_call(req, lambda _r: _model_response(msg))

    events = list(read_events(_events_path(tmp_path, "eng-tok")))
    resp = next(e for e in events if e.type == EventType.LLM_RESPONSE.value)
    assert resp.payload["usage"]["total_tokens"] == 15
    assert resp.payload["stop"] == "stop"


def test_research_trajectory_ships_agent_reasoning_end_to_end(tmp_path: Path, monkeypatch):
    """The whole point of the research tier, exercised through the real path.

    Production shipped 120k trajectory steps with ZERO role='agent' events. Two
    stacked causes: the reasoning lives in thinking blocks (never read), and the
    response is a ModelResponse wrapper (so `.content` was empty anyway). This
    drives the real middleware, with the real wrapper, into a real sink.
    """
    import json as _json

    from langchain_core.messages import AIMessage

    from decepticon.telemetry import config as tconfig
    from decepticon.telemetry.sink import TelemetrySink

    sent: list[dict] = []
    sink = TelemetrySink(
        tconfig.TelemetryConfig(
            mode=tconfig.TelemetryMode.RESEARCH,
            endpoint="https://gw.example",
            install_id="1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
            version="9.9.9",
            os_name="linux",
        ),
        transport=lambda _u, b: sent.append(_json.loads(b)),
    )
    monkeypatch.setattr("decepticon.middleware.event_logging.get_sink", lambda: sink)

    mw = EventLogMiddleware(role="exploit")

    class _Human:
        type = "human"
        content = "<system-reminder>ignore me</system-reminder>\nown the DMZ host"

    # A tool-calling turn: no visible text at all, only the chain-of-thought.
    msg = AIMessage(content=[{"type": "thinking", "thinking": "the login looks injectable"}])
    req = _ModelRequest(
        tmp_path, "eng-traj", messages=[_Human()], model="anthropic/claude-opus-4-8", agent=""
    )
    mw.wrap_model_call(req, lambda _r: _model_response(msg))
    sink.close()

    steps = [e for env in sent for e in env["events"] if e["type"] == "trajectory.step"]
    by_role = {s["role"]: s for s in steps}
    assert set(by_role) == {"human", "agent"}
    assert by_role["human"]["text"] == "own the DMZ host"  # reminder stripped
    assert by_role["agent"]["text"] == "the login looks injectable"  # CoT captured
    assert by_role["agent"]["agent"] == "exploit"
    assert by_role["agent"]["model"] == "anthropic-claude-opus-4-8"
    assert by_role["human"]["step"] == 0 and by_role["agent"]["step"] == 1


def test_tool_call_binds_the_session_for_tool_side_emits(tmp_path: Path, monkeypatch):
    # A tool (the finding path) has no state or run config; without the ambient
    # binding its events shipped with no session and could not be grouped.
    from decepticon.middleware.event_logging import _session_id
    from decepticon.telemetry.sink import current_session

    mw = EventLogMiddleware(role="exploit")
    seen: list[str | None] = []

    def _handler(_r):
        seen.append(current_session())
        return ToolMessage(content="ok", tool_call_id="t", status="success")

    req = _ToolRequest(tmp_path, "eng-ctx", tool="validate_finding", args={}, agent="")
    mw.wrap_tool_call(req, _handler)

    assert seen == [_session_id("eng-ctx")]
    assert current_session() is None  # unbound again after the call


def test_engagement_identity_terms_come_only_from_declarations(tmp_path: Path):
    """The org name is declared, not detected.

    The RoE interview asks for the client organization outright, so there is
    ground truth to match — no word list, no NER, no guessing. Measured in the
    live corpus, the client name leaked verbatim via `/workspace/<slug>` paths.
    """
    import json as _json

    from decepticon.middleware.event_logging import _engagement_identity_terms

    ws = tmp_path / "codeantai-new"
    (ws / "plan").mkdir(parents=True)
    (ws / "plan" / "roe.json").write_text(
        _json.dumps(
            {
                "client": "CodeAnt AI",
                "engagement_slug": "codeantai-new",
                "authorized_by": "Jane Auditor",
                "unrelated": "not an identity field",
            }
        )
    )
    terms = set(_engagement_identity_terms(str(ws)))
    assert {"CodeAnt AI", "codeantai-new", "Jane Auditor"} <= terms
    assert "not an identity field" not in terms  # only declared identity fields

    # No RoE at all -> only the workspace directory, never an invented term.
    bare = tmp_path / "someengagement"
    bare.mkdir()
    assert _engagement_identity_terms(str(bare)) == ["someengagement"]


def test_declared_org_is_masked_in_the_trajectory(tmp_path: Path):
    from decepticon.telemetry.redact import Redactor

    red = Redactor()
    red.add_known(["CodeAnt AI", "codeantai-new"], "ORG")
    out = red.redact("Workspace: /workspace/codeantai-new — the CodeAnt AI portal")
    assert "CodeAnt" not in out
    assert out.count("<ORG_") == 2  # slug and prose name are distinct placeholders
