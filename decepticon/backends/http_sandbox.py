"""HTTP-transport sandbox backend.

`HTTPSandbox` is a `BaseSandbox` subclass that forwards every operation
the agent needs — `execute`, `upload_files`, `download_files`,
`execute_tmux`, `start_background`, `poll_completion`, `kill_session`,
`read_session_log_diff`, `reset_session_log_offset`, `session_log_path` —
to a remote sandbox daemon over HTTP. The peer is
`decepticon.sandbox_server`, a FastAPI app that runs *inside* the
sandbox container and wraps a `LocalSandbox` (a `SandboxBase`
subclass with `docker exec` swapped for direct subprocess execution).

Architecture
------------
The existing `DockerSandbox` shells `docker exec <container> ...` into a
sibling sandbox container — great in dev where a docker daemon is
available, untenable on serverless runtimes (Cloud Run, Fargate, etc.)
that explicitly do not expose a host docker socket between sibling
containers. `HTTPSandbox` keeps **every** semantic of the existing
DockerSandbox + middleware stack — tmux session management, PS1 marker
parsing, size watchdog, auto-background after 60s, session log diff —
and only swaps the wire layer from `docker exec` to HTTP. The daemon
side re-uses the exact same `TmuxSessionManager` class via the new
`exec_prefix=[]` switch, so the agent gets bit-for-bit equivalent
behaviour from the bash tool whether it's pointed at DockerSandbox
(dev / GCE Spot) or HTTPSandbox (Cloud Run multi-container).

Why HTTP and not SSH / gRPC: OpenHands explicitly deprecated SSH
(Issue #2404) because sshd-in-every-image is untenable when users
bring their own sandbox images. E2B, Modal, Daytona, SmolAgents,
SWE-ReX all converged on REST. Cloud Run sibling-container loopback
is HTTP/1.1-first; gRPC needs h2c; SSH needs key distribution + sshd.
REST + SSE has the strongest container-runtime tool support and the
lowest configuration burden.

Class-level state
-----------------
`SandboxNotificationMiddleware` polls `sandbox._jobs.all_jobs()` to
discover which background commands are still running and then calls
`sandbox.poll_completion(...)` to refresh each one. To stay drop-in
compatible with that middleware, `HTTPSandbox` exposes a class-level
`BackgroundJobTracker` populated locally by `start_background` and
refreshed by `poll_completion`. The tracker is a *mirror* — the source
of truth still lives in the daemon's `LocalSandbox._jobs` — but
the middleware doesn't need to know which side owns the registry.
"""

from __future__ import annotations

import asyncio
import base64
from typing import ClassVar

import httpx
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from decepticon.sandbox_kernel import BackgroundJob, BackgroundJobTracker


class HTTPSandbox(BaseSandbox):
    """A `BaseSandbox` that talks to a `decepticon.sandbox_server` daemon.

    The peer endpoint is a FastAPI service running inside the sandbox
    container, typically reachable over Cloud Run's loopback interface
    (`http://localhost:9999` by default) or any service-mesh address
    when deployed on Kubernetes / Fargate / ECS / etc.

    Args:
        base_url: Daemon base URL, e.g. ``http://localhost:9999``. No
            trailing slash required.
        token: Optional shared-secret bearer token. When set, the daemon
            requires every request to carry ``Authorization: Bearer
            <token>``. The Cloud Run loopback path is not network-
            reachable from outside the service, so this is defence-in-
            depth rather than a primary authn mechanism — but it is
            still strongly recommended.
        timeout: Default request timeout in seconds. Per-call timeouts
            on ``execute()`` / ``execute_tmux()`` override this for
            long-running commands.
    """

    # Mirrors `DockerSandbox._jobs` so SandboxNotificationMiddleware can
    # read backed-up background jobs via `sandbox._jobs.all_jobs()`. The
    # registry is local — the actual job execution lives on the daemon
    # side — but `start_background` + `poll_completion` keep the local
    # mirror in sync with the daemon's view.
    _jobs: ClassVar[BackgroundJobTracker] = BackgroundJobTracker()

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def id(self) -> str:
        return f"http-sandbox:{self._base_url}"

    # ── httpx client lifecycle ─────────────────────────────────────────
    def _http(self) -> httpx.Client:
        """Lazily create a connection-pooled HTTP client.

        Sharing one `httpx.Client` across requests is the supported
        pattern — it keeps the TCP connection pool warm so the per-call
        overhead on a healthy loopback path stays in the microseconds
        rather than reopening a socket per request.
        """
        if self._client is None:
            headers = {"User-Agent": "decepticon-http-sandbox/1"}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.Client(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    def close(self) -> None:
        """Best-effort cleanup. Safe to call multiple times."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # ── BaseSandbox abstract methods ───────────────────────────────────
    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        # The per-call request timeout is bumped above `timeout` so the
        # remote has a moment to finish + return after its own command
        # timeout fires. Without this margin, httpx would abort just as
        # the remote was sending the truncated-but-valid response.
        request_timeout = (timeout + 10) if timeout is not None else None
        response = self._http().post(
            "/execute",
            json={"command": command, "timeout": timeout},
            timeout=request_timeout if request_timeout is not None else self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return ExecuteResponse(
            output=data["output"],
            exit_code=data.get("exit_code"),
            truncated=data.get("truncated", False),
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        payload = {
            "files": [
                {
                    "path": path,
                    "data_b64": base64.b64encode(data).decode("ascii"),
                }
                for path, data in files
            ]
        }
        response = self._http().post("/upload_files", json=payload)
        response.raise_for_status()
        data = response.json()
        return [
            FileUploadResponse(path=item["path"], error=item.get("error")) for item in data["files"]
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        response = self._http().post("/download_files", json={"paths": paths})
        response.raise_for_status()
        data = response.json()
        out: list[FileDownloadResponse] = []
        for item in data["files"]:
            content_b64 = item.get("data_b64")
            content = base64.b64decode(content_b64) if content_b64 else None
            out.append(
                FileDownloadResponse(
                    path=item["path"],
                    content=content,
                    error=item.get("error"),
                )
            )
        return out

    # ── tmux / background surface — mirrors DockerSandbox ────────────────
    # These are the methods the bash tool consumes via
    # `decepticon/tools/bash/bash.py:_sandbox.execute_tmux_async(...)`
    # etc. The HTTP transport adds <1ms of overhead on loopback compared
    # to docker-exec; the tmux session state itself lives on the daemon
    # side where TmuxSessionManager always lived.

    def execute_tmux(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
        workspace_path: str | None = None,
    ) -> str:
        """Run `command` in the named tmux session and return the output.

        Mirrors `DockerSandbox.execute_tmux`. See that class for the full
        protocol contract (PS1 markers, size watchdog, auto-background
        after 60 s, output truncation at 30 K chars).
        """
        request_timeout = (timeout + 10) if timeout is not None else None
        response = self._http().post(
            "/execute_tmux",
            json={
                "command": command,
                "session": session,
                "timeout": timeout,
                "is_input": is_input,
                "workspace_path": workspace_path,
            },
            timeout=request_timeout if request_timeout is not None else self._timeout,
        )
        response.raise_for_status()
        return response.json()["output"]

    async def execute_tmux_async(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
        workspace_path: str | None = None,
        on_auto_background=None,
    ) -> str:
        """Async wrapper around `execute_tmux`.

        DockerSandbox.execute_tmux_async is cancellable via
        `asyncio.CancelledError` — when the supervisor's task() call gets
        cancelled mid-run, the bash command is auto-backgrounded. We
        approximate that here by running the sync call in a thread so
        cancellation cleanly propagates through `httpx`'s timeout
        machinery. The remote daemon's own auto-background timer
        (`AUTO_BACKGROUND_SECONDS = 60 s`) still fires on its side, so
        long-running commands are tracked as background jobs even if the
        client disconnects.

        `on_auto_background` is accepted for signature parity with
        DockerSandbox but currently isn't invoked — the daemon already
        records the background-job state itself, and `poll_completion`
        on the next middleware tick surfaces it.
        """
        _ = on_auto_background  # signature parity; behaviour deferred
        return await asyncio.to_thread(
            self.execute_tmux,
            command=command,
            session=session,
            timeout=timeout,
            is_input=is_input,
            workspace_path=workspace_path,
        )

    def start_background(
        self,
        command: str,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> None:
        """Launch `command` in the background; register a local mirror job."""
        response = self._http().post(
            "/start_background",
            json={
                "command": command,
                "session": session,
                "workspace_path": workspace_path,
            },
        )
        response.raise_for_status()
        # The daemon owns the canonical BackgroundJob (it just stamped
        # `initial_markers` from the live tmux pane state, which we
        # don't have visibility into). Drop a provisional entry into
        # the local mirror so SandboxNotificationMiddleware's
        # iteration can find it; `poll_completion` will replace the
        # stub's status / exit_code on the next refresh tick.
        ws = workspace_path or "/workspace"
        self._jobs.register(
            session=session,
            command=command,
            initial_markers=0,
            workspace_path=ws,
        )

    def poll_completion(
        self,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> BackgroundJob | None:
        """Return the latest BackgroundJob for `session` (None if missing)."""
        response = self._http().post(
            "/poll_completion",
            json={"session": session, "workspace_path": workspace_path},
        )
        response.raise_for_status()
        data = response.json()
        if data.get("job") is None:
            return None
        j = data["job"]
        job = BackgroundJob(
            session=j["session"],
            key=j["key"],
            command=j["command"],
            initial_markers=j["initial_markers"],
            started_at=j["started_at"],
            workspace_path=j.get("workspace_path", "/workspace"),
            status=j.get("status", "running"),
            exit_code=j.get("exit_code"),
            completed_at=j.get("completed_at"),
            consumed=j.get("consumed", False),
        )
        # Keep the local mirror coherent: refresh status from the
        # daemon's view so ``BackgroundJobTracker.pending_completions``
        # surfaces this job to SandboxNotificationMiddleware on its next
        # tick. Dedupe of already-emitted completions is handled by
        # ``mark_consumed`` (the middleware calls it post-emit) — not by
        # removing from the mirror, which would make the done state
        # invisible to ``pending_completions`` entirely.
        local = self._jobs.get(session=job.session)
        if local is None:
            # Stub entry was never registered (e.g. start_background was
            # called from a different agent process, or the local mirror
            # was cleared). Re-register so subsequent polls find it.
            self._jobs.register(
                session=job.session,
                command=job.command,
                initial_markers=job.initial_markers,
                workspace_path=job.workspace_path,
            )
            local = self._jobs.get(session=job.session)
        if local is not None and job.status != "running":
            # The daemon reports exit_code as ``int | None``; if the job
            # raced past completion before its exit code was captured,
            # fall back to ``-1`` so the local mirror still flips to
            # ``done`` and the notification path can fire.
            self._jobs.mark_complete(
                session=job.session,
                exit_code=job.exit_code if job.exit_code is not None else -1,
                key=local.key,
            )
        return job

    def kill_session(
        self,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> None:
        response = self._http().post(
            "/kill_session",
            json={"session": session, "workspace_path": workspace_path},
        )
        response.raise_for_status()

    def read_session_log_diff(
        self,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> str:
        response = self._http().post(
            "/read_session_log_diff",
            json={"session": session, "workspace_path": workspace_path},
        )
        response.raise_for_status()
        return response.json()["diff"]

    def reset_session_log_offset(
        self,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> None:
        response = self._http().post(
            "/reset_session_log_offset",
            json={"session": session, "workspace_path": workspace_path},
        )
        response.raise_for_status()

    def session_log_path(
        self,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> str:
        response = self._http().post(
            "/session_log_path",
            json={"session": session, "workspace_path": workspace_path},
        )
        response.raise_for_status()
        return response.json()["path"]
