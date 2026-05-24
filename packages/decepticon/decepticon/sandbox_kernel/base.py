"""Shared sandbox implementation — used by both DockerSandbox
(agent-side, ``docker exec`` transport) and LocalSandbox (sandbox-side,
direct subprocess inside the daemon container).

`SandboxBase` holds every method that is invariant across the two
transports — tmux session management, workspace path normalization,
background-job tracking, log-offset diff, `execute()` (which already
uses `self._exec_prefix`), and the full tmux/background surface
(`execute_tmux`, `start_background`, `poll_completion`, etc.). The two
real backends below it implement just the file-transfer pair
(`upload_files`, `download_files`) — the only thing whose mechanics
genuinely differ between docker-exec (uses `docker cp`) and in-
container local execution (uses pathlib).

Class-level state (`_jobs`, `_log_offsets`) is intentionally redeclared
on each concrete subclass so the SandboxNotificationMiddleware's
`getattr(sandbox, "_jobs")` lookup pulls the subclass-specific tracker
rather than a shared base singleton.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import subprocess
import threading
from typing import ClassVar

from deepagents.backends.protocol import ExecuteResponse
from deepagents.backends.sandbox import BaseSandbox

from decepticon.sandbox_kernel.jobs import BackgroundJob, BackgroundJobTracker
from decepticon.sandbox_kernel.tmux import PS1_PATTERN, TmuxSessionManager, _safe_log

log = logging.getLogger("decepticon.sandbox_kernel.base")


class SandboxBase(BaseSandbox):
    """deepagents BaseSandbox backed by a running Docker container.

    File operations (ls, read, write, edit, grep, glob) are handled by
    BaseSandbox, which delegates them to execute() — simple, non-interactive
    docker exec calls sufficient for atomic file ops.

    The bash tool uses execute_tmux() for persistent tmux sessions that
    support interactive input.

    ``_jobs`` and ``_log_offsets`` are class-level so every agent factory
    in a process talks to the same background-job tracker — the bash tool
    (which reads a module-global ``_sandbox`` set by whichever factory ran
    last) and the SandboxNotificationMiddleware (bound to a different
    instance per agent) would otherwise see disjoint trackers and
    completion notifications would never fire.
    """

    _jobs: ClassVar[BackgroundJobTracker] = BackgroundJobTracker()
    _log_offsets: ClassVar[dict[str, int]] = {}
    _log_offsets_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(
        self,
        container_name: str = "decepticon-sandbox",
        default_timeout: int = 120,
        workspace_path: str = "/workspace",
        exec_prefix: list[str] | None = None,
    ) -> None:
        self._container_name = container_name
        self._default_timeout = default_timeout
        self._workspace_path = self._normalize_workspace_path(workspace_path)
        self._managers: dict[str, TmuxSessionManager] = {}
        self._managers_lock = threading.RLock()
        # When None: keep the default `docker exec <ctn>` prefix so
        # nothing changes for existing callers. The HTTP sandbox daemon
        # — which runs *inside* the sandbox container — passes
        # `exec_prefix=[]` (or instantiates LocalSandbox) so the
        # same tmux/exec/upload code path is reused without a nested
        # docker daemon.
        self._exec_prefix: list[str] = (
            list(exec_prefix) if exec_prefix is not None else ["docker", "exec", container_name]
        )

    @staticmethod
    def _normalize_workspace_path(workspace_path: str | None) -> str:
        path = (workspace_path or "/workspace").strip()
        if path == "/workspace":
            return path
        if not path.startswith("/workspace/"):
            return "/workspace"
        path = path.rstrip("/")
        components = path[len("/workspace/") :].split("/")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", component) for component in components):
            return "/workspace"
        return path

    @staticmethod
    def _workspace_slug(workspace_path: str) -> str:
        path = SandboxBase._normalize_workspace_path(workspace_path)
        if path == "/workspace":
            return "root"
        digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:8]
        slug = path.rsplit("/", 1)[-1] or "workspace"
        safe_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", slug).strip("-") or "workspace"
        return f"{safe_slug}-{digest}"

    def _workspace_key(self, workspace_path: str | None = None) -> str:
        return self._workspace_slug(workspace_path or self._workspace_path)

    def _manager_key(self, session: str, workspace_path: str) -> str:
        if self._normalize_workspace_path(workspace_path) == "/workspace":
            return session
        return f"{self._workspace_key(workspace_path)}:{session}"

    @staticmethod
    def _tmux_session_name(session: str, workspace_path: str) -> str:
        if SandboxBase._normalize_workspace_path(workspace_path) == "/workspace":
            return SandboxBase._safe_session_name(session)
        workspace_key = SandboxBase._workspace_slug(workspace_path)
        safe_session = SandboxBase._safe_session_name(session)
        return f"dcptn_{workspace_key}_{safe_session}"

    @staticmethod
    def _safe_session_name(session: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "-", session).strip("-") or "main"

    def session_log_path(self, session: str, workspace_path: str | None = None) -> str:
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        return f"{effective_workspace}/.sessions/{self._safe_session_name(session)}.log"

    def _get_manager(
        self,
        session: str,
        workspace_path: str | None = None,
    ) -> TmuxSessionManager:
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        key = self._manager_key(session, effective_workspace)
        tmux_session = self._tmux_session_name(session, effective_workspace)
        log_name = f"{self._safe_session_name(session)}"
        with self._managers_lock:
            if key not in self._managers:
                self._managers[key] = TmuxSessionManager(
                    tmux_session,
                    self._container_name,
                    workspace_path=effective_workspace,
                    log_name=log_name,
                    exec_prefix=self._exec_prefix,
                )
            return self._managers[key]

    # ── BaseSandbox abstract methods ──────────────────────────────────────

    @property
    def id(self) -> str:
        return self._container_name

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Simple docker exec — used by BaseSandbox for file operations."""
        effective = timeout if timeout is not None else self._default_timeout
        try:
            result = subprocess.run(
                [*self._exec_prefix, "sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=effective,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout
            if result.stderr and result.stderr.strip():
                output += f"\n<stderr>{result.stderr.strip()}</stderr>"
            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=False,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Command timed out after {effective}s",
                exit_code=124,
                truncated=False,
            )

    def read_session_log_diff(self, session: str, workspace_path: str | None = None) -> str:
        """Return new bytes appended to <workspace>/.sessions/<session>.log
        since the previous call (or the whole file on first call).

        Per-process offset tracking only — restart resets to 0 (safe fallback).
        File truncation/rotation also resets to 0.
        """
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        key = self._manager_key(session, effective_workspace)
        log_path = self.session_log_path(session, effective_workspace)
        results = self.download_files([log_path])
        if not results or results[0].error or results[0].content is None:
            return ""
        full = results[0].content
        with self._log_offsets_lock:
            prev_offset = self._log_offsets.get(key, 0)
            if prev_offset > len(full):
                prev_offset = 0
            new_bytes = full[prev_offset:]
            self._log_offsets[key] = len(full)
        return new_bytes.decode("utf-8", errors="replace")

    def reset_session_log_offset(self, session: str, workspace_path: str | None = None) -> None:
        """Forget the read offset (used after kill / GC)."""
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        key = self._manager_key(session, effective_workspace)
        with self._log_offsets_lock:
            self._log_offsets.pop(key, None)

    # ── Tmux execution (for bash tool) ───────────────────────────────────

    def execute_tmux(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
        workspace_path: str | None = None,
    ) -> str:
        """Tmux-based execution with session persistence and interactive support.

        Used exclusively by the bash tool. Supports:
        - Named sessions for parallel command execution
        - Interactive input (y/n, passwords, C-c / C-z / C-d)
        - Output truncation for large outputs
        """
        effective = timeout if timeout is not None else self._default_timeout
        mgr = self._get_manager(session, workspace_path)

        if not command and not is_input:
            return mgr.read_screen()

        return mgr.execute(
            command,
            is_input=is_input,
            timeout=effective,
        )

    async def execute_tmux_async(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
        workspace_path: str | None = None,
    ) -> str:
        """Async tmux execution — cancellable via asyncio.CancelledError.

        Used by the async bash tool so that LangGraph run cancellation
        (Ctrl+C → cancelMany) interrupts the polling loop promptly.
        """
        effective = timeout if timeout is not None else self._default_timeout
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        job_key = self._manager_key(session, effective_workspace)
        mgr = self._get_manager(session, effective_workspace)

        if not command and not is_input:
            return await asyncio.to_thread(mgr.read_screen)

        def _on_auto_background(cmd: str, baseline: str) -> None:
            self._jobs.register(
                session,
                command=cmd,
                initial_markers=len(PS1_PATTERN.findall(baseline)),
                key=job_key,
                workspace_path=effective_workspace,
            )

        return await mgr.execute_async(
            command,
            is_input=is_input,
            timeout=effective,
            on_auto_background=_on_auto_background,
        )

    def start_background(
        self,
        command: str,
        session: str = "main",
        workspace_path: str | None = None,
    ) -> None:
        """Launch a command in a named tmux session without blocking.

        Registers a BackgroundJob keyed by the PS1-marker count at launch;
        ``poll_completion`` later compares against this baseline.
        """
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        job_key = self._manager_key(session, effective_workspace)
        mgr = self._get_manager(session, effective_workspace)
        mgr.initialize()
        baseline = mgr._capture()
        initial_markers = len(PS1_PATTERN.findall(baseline))
        self._jobs.register(
            session,
            command=command,
            initial_markers=initial_markers,
            key=job_key,
            workspace_path=effective_workspace,
        )
        mgr._send(command, enter=True)

    def poll_completion(
        self,
        session: str,
        workspace_path: str | None = None,
    ) -> "BackgroundJob | None":
        """Check whether a background job has produced a new PS1 marker.

        Updates the tracker in place; returns the job (or None if not tracked).
        Capture failures are swallowed — the job stays running, retried later.
        """
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        job_key = self._manager_key(session, effective_workspace)
        job = self._jobs.get(session, key=job_key)
        if job is None or job.status != "running":
            return job
        try:
            mgr = self._get_manager(session, effective_workspace)
            screen = mgr._capture()
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            return job
        markers = list(PS1_PATTERN.finditer(screen))
        if len(markers) > job.initial_markers:
            try:
                exit_code = int(markers[-1].group(1))
            except ValueError:
                exit_code = -1
            self._jobs.mark_complete(session, exit_code=exit_code, key=job_key)
        return job

    def kill_session(self, session: str, workspace_path: str | None = None) -> None:
        """Send Ctrl+C, then kill the tmux session, then clear all caches.

        Best-effort: errors are logged, not raised. The pipe-pane log file
        is preserved at <engagement>/.sessions/<session>.log for audit.
        """
        effective_workspace = self._normalize_workspace_path(workspace_path or self._workspace_path)
        manager_key = self._manager_key(session, effective_workspace)
        mgr: TmuxSessionManager | None = None
        try:
            mgr = self._get_manager(session, effective_workspace)
            try:
                mgr._docker_tmux(["send-keys", "-t", mgr.session, "C-c"])
            except RuntimeError as e:
                log.debug("send-keys C-c failed for '%s': %s", _safe_log(session), _safe_log(e))
            try:
                mgr._docker_tmux(["kill-session", "-t", mgr.session])
            except RuntimeError as e:
                log.warning("kill-session failed for '%s': %s", _safe_log(session), _safe_log(e))
        finally:
            with self._managers_lock:
                self._managers.pop(manager_key, None)
            if mgr is not None:
                with TmuxSessionManager._init_lock:
                    TmuxSessionManager._initialized.discard(mgr.session)
            self.reset_session_log_offset(session, effective_workspace)
            self._jobs.remove(session, key=manager_key)


# ─── Pre-flight check ────────────────────────────────────────────────────
