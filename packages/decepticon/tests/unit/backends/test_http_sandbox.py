"""Unit tests for the HTTP-transport sandbox backend (``HTTPSandbox``).

Every method on ``HTTPSandbox`` forwards a JSON request to the in-container
``decepticon.sandbox_server`` daemon and parses the JSON reply. The tests
inject an ``httpx.MockTransport`` so the full request-build / response-parse
path runs without a live daemon, and exercise the retry/back-off helper and
the domain-error wrapping in isolation.
"""

from __future__ import annotations

import httpx
import pytest

from decepticon.backends.http_sandbox import (
    HTTPSandbox,
    SandboxError,
    _retry_on_connection_error,
)
from decepticon.sandbox_kernel import BackgroundJobTracker


class _Recorder:
    """Routes mock requests by path and records each one for assertions."""

    def __init__(self, routes: dict[str, object]):
        self._routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = self._routes.get(request.url.path, {})
        if isinstance(body, httpx.Response):
            return body
        if callable(body):
            return body(request)
        return httpx.Response(200, json=body)

    def last_json(self) -> dict:
        import json as _json

        return _json.loads(self.requests[-1].content)


def _make(routes: dict[str, object], *, token: str | None = None) -> tuple[HTTPSandbox, _Recorder]:
    """Build an ``HTTPSandbox`` whose client is wired to a mock transport."""
    rec = _Recorder(routes)
    sb = HTTPSandbox("http://localhost:9999/", token=token)
    headers = {"User-Agent": "decepticon-http-sandbox/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    sb._client = httpx.Client(
        transport=httpx.MockTransport(rec),
        base_url="http://localhost:9999",
        headers=headers,
    )
    return sb, rec


# ── _retry_on_connection_error ───────────────────────────────────────────────


def test_retry_returns_immediately_on_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert _retry_on_connection_error(fn) == "ok"
    assert calls["n"] == 1


def test_retry_recovers_after_transient_connect_error(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("decepticon.backends.http_sandbox.time.sleep", slept.append)
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("boom")
        return "recovered"

    assert _retry_on_connection_error(fn, max_retries=3, base_delay=0.5) == "recovered"
    assert attempts["n"] == 3
    # Exponential back-off: 0.5 * 2**0, then 0.5 * 2**1.
    assert slept == [0.5, 1.0]


def test_retry_raises_last_exception_when_exhausted(monkeypatch):
    monkeypatch.setattr("decepticon.backends.http_sandbox.time.sleep", lambda _d: None)

    def fn():
        raise httpx.ConnectTimeout("still down")

    with pytest.raises(httpx.ConnectTimeout, match="still down"):
        _retry_on_connection_error(fn, max_retries=2)


def test_retry_does_not_swallow_non_connection_errors():
    def fn():
        raise ValueError("not retryable")

    with pytest.raises(ValueError, match="not retryable"):
        _retry_on_connection_error(fn)


# ── construction + client lifecycle ──────────────────────────────────────────


def test_base_url_trailing_slash_is_stripped():
    sb = HTTPSandbox("http://host:9999/")
    assert sb._base_url == "http://host:9999"
    assert sb.id == "http-sandbox:http://host:9999"


def test_http_client_is_lazy_and_cached():
    sb = HTTPSandbox("http://host:9999")
    assert sb._client is None
    client = sb._http()
    assert client is sb._http()  # cached, not rebuilt per call
    sb.close()


def test_http_client_sets_token_header_when_provided():
    sb = HTTPSandbox("http://host:9999", token="s3cret")
    client = sb._http()
    assert client.headers["Authorization"] == "Bearer s3cret"
    assert client.headers["User-Agent"] == "decepticon-http-sandbox/1"
    sb.close()


def test_http_client_omits_auth_header_without_token():
    sb = HTTPSandbox("http://host:9999")
    assert "authorization" not in sb._http().headers
    sb.close()


def test_close_is_idempotent():
    sb = HTTPSandbox("http://host:9999")
    sb._http()
    sb.close()
    assert sb._client is None
    sb.close()  # second call must not raise


def test_each_instance_has_its_own_job_tracker():
    a = HTTPSandbox("http://host:9999")
    b = HTTPSandbox("http://host:9999")
    assert isinstance(a._jobs, BackgroundJobTracker)
    assert a._jobs is not b._jobs


# ── _request error handling ──────────────────────────────────────────────────


def test_request_wraps_http_error_status_in_sandbox_error():
    sb, _ = _make({"/execute": httpx.Response(500, text="daemon exploded")})
    with pytest.raises(SandboxError) as ei:
        sb.execute("whoami")
    assert "500" in str(ei.value)
    assert "daemon exploded" in str(ei.value)


def test_request_error_body_is_truncated_to_200_chars():
    sb, _ = _make({"/kill_session": httpx.Response(503, text="x" * 500)})
    with pytest.raises(SandboxError) as ei:
        sb.kill_session()
    # The body snippet is truncated to 200 chars (the full payload is 500).
    msg = str(ei.value)
    prefix = "Sandbox returned 503: "
    assert msg.startswith(prefix)
    assert len(msg) - len(prefix) == 200


def test_request_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("decepticon.backends.http_sandbox.time.sleep", lambda _d: None)
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectError("cold start")
        return httpx.Response(200, json={"output": "hi", "exit_code": 0})

    sb = HTTPSandbox("http://localhost:9999")
    sb._client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://localhost:9999"
    )
    assert sb.execute("echo hi").output == "hi"
    assert state["n"] == 2


# ── execute ──────────────────────────────────────────────────────────────────


def test_execute_parses_full_response():
    sb, rec = _make({"/execute": {"output": "root\n", "exit_code": 0, "truncated": True}})
    resp = sb.execute("id")
    assert resp.output == "root\n"
    assert resp.exit_code == 0
    assert resp.truncated is True
    assert rec.last_json() == {"command": "id", "timeout": None}


def test_execute_defaults_truncated_and_exit_code():
    sb, _ = _make({"/execute": {"output": "x"}})
    resp = sb.execute("id")
    assert resp.exit_code is None
    assert resp.truncated is False


def test_execute_bumps_request_timeout_above_command_timeout(monkeypatch):
    captured: dict = {}

    def fake_request(method, path, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={"output": ""})

    sb = HTTPSandbox("http://host:9999")
    monkeypatch.setattr(sb, "_request", fake_request)
    sb.execute("sleep 30", timeout=30)
    assert captured["timeout"] == 40  # command timeout + 10s margin
    assert captured["json"]["timeout"] == 30


def test_execute_uses_default_timeout_when_unset(monkeypatch):
    captured: dict = {}

    def fake_request(method, path, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={"output": ""})

    sb = HTTPSandbox("http://host:9999", timeout=77.0)
    monkeypatch.setattr(sb, "_request", fake_request)
    sb.execute("id")
    assert captured["timeout"] == 77.0


# ── upload / download (base64 round-trip) ────────────────────────────────────


def test_upload_files_base64_encodes_payload():
    sb, rec = _make({"/upload_files": {"files": [{"path": "/tmp/a"}]}})
    out = sb.upload_files([("/tmp/a", b"hello")])
    assert out[0].path == "/tmp/a"
    assert out[0].error is None
    sent = rec.last_json()["files"][0]
    assert sent["path"] == "/tmp/a"
    import base64

    assert base64.b64decode(sent["data_b64"]) == b"hello"


def test_upload_files_surfaces_per_file_error():
    sb, _ = _make({"/upload_files": {"files": [{"path": "/x", "error": "EACCES"}]}})
    out = sb.upload_files([("/x", b"")])
    assert out[0].error == "EACCES"


def test_download_files_decodes_base64_content():
    import base64

    payload = base64.b64encode(b"world").decode("ascii")
    sb, rec = _make({"/download_files": {"files": [{"path": "/f", "data_b64": payload}]}})
    out = sb.download_files(["/f"])
    assert out[0].content == b"world"
    assert rec.last_json() == {"paths": ["/f"]}


def test_download_files_missing_data_yields_none_content():
    sb, _ = _make({"/download_files": {"files": [{"path": "/f", "error": "missing"}]}})
    out = sb.download_files(["/f"])
    assert out[0].content is None
    assert out[0].error == "missing"


# ── tmux surface ─────────────────────────────────────────────────────────────


def test_execute_tmux_returns_output_and_sends_session():
    sb, rec = _make({"/execute_tmux": {"output": "pane-text"}})
    assert sb.execute_tmux("ls", session="work") == "pane-text"
    body = rec.last_json()
    assert body["command"] == "ls"
    assert body["session"] == "work"
    assert body["is_input"] is False


def test_execute_tmux_timeout_margin(monkeypatch):
    captured: dict = {}

    def fake_request(method, path, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={"output": ""})

    sb = HTTPSandbox("http://host:9999")
    monkeypatch.setattr(sb, "_request", fake_request)
    sb.execute_tmux("top", timeout=5)
    assert captured["timeout"] == 15


async def test_execute_tmux_async_delegates_to_sync():
    sb, rec = _make({"/execute_tmux": {"output": "async-out"}})
    result = await sb.execute_tmux_async("ps", session="bg")
    assert result == "async-out"
    assert rec.last_json()["session"] == "bg"


# ── background jobs ──────────────────────────────────────────────────────────


def test_start_background_registers_local_mirror():
    sb, rec = _make({"/start_background": {}})
    sb.start_background("nmap -p- target", session="scan")
    job = sb._jobs.get("scan")
    assert job is not None
    assert job.command == "nmap -p- target"
    assert job.workspace_path == "/workspace"
    assert rec.last_json()["session"] == "scan"


def test_start_background_honors_explicit_workspace():
    sb, _ = _make({"/start_background": {}})
    sb.start_background("sleep 100", session="s", workspace_path="/opt/work")
    job = sb._jobs.get("s")
    assert job is not None
    assert job.workspace_path == "/opt/work"


def test_poll_completion_returns_none_when_daemon_has_no_job():
    sb, _ = _make({"/poll_completion": {"job": None}})
    assert sb.poll_completion("idle") is None


def test_poll_completion_marks_local_mirror_done():
    job_payload = {
        "job": {
            "session": "s",
            "key": "s",
            "command": "scan",
            "initial_markers": 0,
            "started_at": 1.0,
            "status": "done",
            "exit_code": 0,
        }
    }
    sb, _ = _make({"/poll_completion": job_payload})
    sb._jobs.register(session="s", command="scan", initial_markers=0, workspace_path="/workspace")
    job = sb.poll_completion("s")
    assert job is not None
    assert job.status == "done"
    assert job.exit_code == 0
    local = sb._jobs.get("s")
    assert local is not None
    assert local.status == "done"


def test_poll_completion_reregisters_missing_local_job():
    job_payload = {
        "job": {
            "session": "ghost",
            "key": "ghost",
            "command": "echo",
            "initial_markers": 2,
            "started_at": 1.0,
            "status": "running",
        }
    }
    sb, _ = _make({"/poll_completion": job_payload})
    assert sb._jobs.get("ghost") is None
    job = sb.poll_completion("ghost")
    assert job is not None
    assert job.status == "running"
    # A running job with no prior local entry gets a stub registered.
    assert sb._jobs.get("ghost") is not None


def test_poll_completion_exit_code_fallback_to_minus_one():
    job_payload = {
        "job": {
            "session": "s",
            "key": "s",
            "command": "scan",
            "initial_markers": 0,
            "started_at": 1.0,
            "status": "done",
            "exit_code": None,
        }
    }
    sb, _ = _make({"/poll_completion": job_payload})
    sb._jobs.register(session="s", command="scan", initial_markers=0, workspace_path="/workspace")
    sb.poll_completion("s")
    local = sb._jobs.get("s")
    assert local is not None
    assert local.exit_code == -1


# ── remaining post endpoints ─────────────────────────────────────────────────


def test_kill_session_posts_session():
    sb, rec = _make({"/kill_session": {}})
    sb.kill_session(session="dead")
    assert rec.last_json()["session"] == "dead"


def test_read_session_log_diff_returns_diff():
    sb, _ = _make({"/read_session_log_diff": {"diff": "+ new line\n"}})
    assert sb.read_session_log_diff(session="m") == "+ new line\n"


def test_reset_session_log_offset_posts():
    sb, rec = _make({"/reset_session_log_offset": {}})
    sb.reset_session_log_offset(session="m", workspace_path="/w")
    body = rec.last_json()
    assert body["session"] == "m"
    assert body["workspace_path"] == "/w"


def test_session_log_path_returns_path():
    sb, _ = _make({"/session_log_path": {"path": "/workspace/.sessions/m.log"}})
    assert sb.session_log_path(session="m") == "/workspace/.sessions/m.log"
