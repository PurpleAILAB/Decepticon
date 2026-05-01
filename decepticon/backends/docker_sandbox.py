"""Docker sandbox backend for deepagents.

Implements BaseSandbox using the Docker CLI, with tmux-based execution
for persistent, interactive shell sessions (used by the bash tool).

Architecture:
    DockerSandbox.execute()       → simple docker exec (used by BaseSandbox
                                    file ops: ls, read, write, edit, grep, glob)
    DockerSandbox.execute_tmux()  → tmux session-based (used by bash tool)
                                    supports: session persistence, interactive input
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import io
import logging
import os
import re
import subprocess
import tarfile
import tempfile
import threading
import time
from collections.abc import Callable
from typing import ClassVar

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

log = logging.getLogger("decepticon.backends.docker_sandbox")


@functools.lru_cache(maxsize=1)
def _docker_cfg():
    """Lazy-load DockerConfig to avoid import-time side effects."""
    from decepticon.core.config import load_config

    return load_config().docker


# ─── Tunable timing constants (patched in tests) ────────────────────────

PS1_PATTERN = re.compile(r"\[DCPTN:(\d+):(.+?)\]")

POLL_INTERVAL: float = 0.5
STALL_SECONDS: float = 3.0
MAX_OUTPUT_CHARS: int = 30_000
AUTO_BACKGROUND_SECONDS: float = 60.0
SIZE_WATCHDOG_CHARS: int = 5_000_000
SIZE_WATCHDOG_INTERVAL: float = 5.0

# ─── Semantic exit code interpretation (Claude Code best practice) ────────
_EXIT_CODE_MESSAGES: dict[int, str] = {
    1: "general error",
    2: "misuse of shell builtin",
    126: "permission denied (not executable)",
    127: "command not found — tool may not be installed (try: apt-get install -y <pkg>)",
    128: "invalid exit argument",
    130: "interrupted by Ctrl+C (SIGINT)",
    137: "killed (SIGKILL) — likely OOM or size limit exceeded",
    139: "segmentation fault (SIGSEGV)",
    143: "terminated (SIGTERM)",
}


def _interpret_exit_code(code: int) -> str:
    """Convert exit code to human-readable message for agent context."""
    if code == 0:
        return ""
    if code in _EXIT_CODE_MESSAGES:
        return f" — {_EXIT_CODE_MESSAGES[code]}"
    if code > 128:
        signal_num = code - 128
        return f" — killed by signal {signal_num}"
    return ""


# ─── TmuxSessionManager ───────────────────────────────────────────────────


class TmuxSessionManager:
    """Manages a single named tmux session inside the Docker container.

    Transplanted from tools/bash/tool.py; docker exec calls now go directly
    through subprocess instead of the old run_in_sandbox() helper.

    Thread-safety: ``_initialized`` is process-wide shared state. The
    ``_init_lock`` (threading.RLock) guards add/discard/clear so concurrent
    sessions cannot race during init or cache invalidation.
    """

    _initialized: set[str] = set()
    _init_lock: threading.RLock = threading.RLock()

    def __init__(self, session: str, container_name: str) -> None:
        self.session = session
        self._container = container_name

    # ── docker / tmux helpers ──

    def _docker_tmux(self, args: list[str], timeout: int = 10) -> str:
        """Run a tmux subcommand inside the container."""
        result = subprocess.run(
            ["docker", "exec", self._container, "tmux"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            # Detect tmux server death and invalidate session cache
            if "no server running" in error_msg or "server exited" in error_msg:
                log.warning("tmux server died — invalidating all session caches")
                with TmuxSessionManager._init_lock:
                    TmuxSessionManager._initialized.clear()
            raise RuntimeError(error_msg)
        return result.stdout

    def _send(self, text: str, enter: bool = True) -> None:
        """Send keystrokes using -l (literal) to prevent tmux escaping bugs."""
        self._docker_tmux(["send-keys", "-t", self.session, "-l", text])
        if enter:
            self._docker_tmux(["send-keys", "-t", self.session, "Enter"])

    def _clear_screen(self) -> None:
        self._docker_tmux(["send-keys", "-t", self.session, "C-l"])
        time.sleep(0.1)
        self._docker_tmux(["clear-history", "-t", self.session])

    def _capture(self) -> str:
        return self._docker_tmux(
            [
                "capture-pane",
                "-J",
                "-p",
                "-S",
                "-",
                "-E",
                "-",
                "-t",
                self.session,
            ]
        )

    # ── session lifecycle ──

    def initialize(self) -> None:
        """Create session if needed and inject PS1 marker (once per session)."""
        with TmuxSessionManager._init_lock:
            if self.session in TmuxSessionManager._initialized:
                return

        session_exists = False
        try:
            self._docker_tmux(["has-session", "-t", self.session], timeout=5)
            session_exists = True
        except RuntimeError:
            session_exists = False

        if not session_exists:
            log.info("Creating tmux session: %s", self.session)
            try:
                self._docker_tmux(["new-session", "-d", "-s", self.session])
            except RuntimeError as e:
                # "duplicate session" — has-session check was stale; session exists
                if "duplicate session" not in str(e):
                    raise
                log.debug("Session %s already exists (race), reusing", self.session)
            time.sleep(0.3)

        # Inject PS1 marker + disable PS2 + clear screen
        ps1_cmd = "export PROMPT_COMMAND='export PS1=\"[DCPTN:$?:$PWD] \"'; export PS2=''; clear"
        self._send(ps1_cmd)
        time.sleep(0.5)
        self._clear_screen()
        time.sleep(0.2)

        if not session_exists:
            log_path = f"/workspace/.sessions/{self.session}.log"
            try:
                # Idempotent — the directory is bind-mounted to the host so
                # operators can tail the same file the agent reads.
                subprocess.run(
                    ["docker", "exec", self._container, "mkdir", "-p", "/workspace/.sessions"],
                    capture_output=True,
                    timeout=5,
                    check=True,
                )
                self._docker_tmux(
                    [
                        "pipe-pane",
                        "-t",
                        self.session,
                        "-o",
                        f"cat >> {log_path}",
                    ]
                )
            except Exception as e:
                log.warning("pipe-pane setup failed for session '%s': %s", self.session, e)

        with TmuxSessionManager._init_lock:
            TmuxSessionManager._initialized.add(self.session)

    # ── execution ──

    def execute(
        self,
        command: str,
        is_input: bool,
        timeout: int,
    ) -> str:
        """Send a command/input and poll for PS1 completion marker.

        Polls until the PS1 marker appears (command complete) or *timeout*
        is reached.  If the tmux session is dead, attempts one automatic
        recovery before returning an error.
        """
        if not is_input:
            self.initialize()

        try:
            baseline = self._capture()
        except RuntimeError as e:
            error_msg = str(e)
            if "no server running" in error_msg or "session not found" in error_msg:
                log.warning("Session '%s' is dead — attempting recovery", self.session)
                with TmuxSessionManager._init_lock:
                    TmuxSessionManager._initialized.discard(self.session)
                try:
                    self.initialize()
                    baseline = self._capture()
                except (RuntimeError, OSError, subprocess.TimeoutExpired) as retry_err:
                    return (
                        f"[ERROR] Session recovery failed: {retry_err}\n"
                        f"The tmux session was destroyed or docker is overloaded. "
                        f"Try using a different session name."
                    )
            else:
                return f"[ERROR] Sandbox error: {e}"
        except (OSError, subprocess.TimeoutExpired) as e:
            return (
                f"[ERROR] Sandbox capture failed: {e}\n"
                f"docker exec timed out or the tmux session is hung. "
                f'Retry, or terminate with bash_kill(session="{self.session}").'
            )

        initial_count = len(PS1_PATTERN.findall(baseline))

        if command:
            if is_input:
                if command in ("C-c", "C-z", "C-d"):
                    self._docker_tmux(["send-keys", "-t", self.session, command])
                else:
                    self._send(command, enter=True)
            else:
                self._send(command, enter=True)

        start = time.monotonic()
        prev_screen = baseline
        last_change_time = start

        while time.monotonic() - start < timeout:
            time.sleep(POLL_INTERVAL)
            try:
                screen = self._capture()
            except RuntimeError as poll_err:
                if "no server running" in str(poll_err):
                    with TmuxSessionManager._init_lock:
                        TmuxSessionManager._initialized.discard(self.session)
                    return (
                        f"[ERROR] tmux session '{self.session}' was destroyed mid-command.\n"
                        f"The command likely killed the shell process (e.g. pkill bash).\n"
                        f"Session will auto-recover on next bash() call."
                    )
                # Other RuntimeError — keep polling, reset stall timer
                log.debug("transient RuntimeError in poll loop: %s", poll_err)
                last_change_time = time.monotonic()
                continue
            except (OSError, subprocess.TimeoutExpired) as poll_err:
                # docker exec stall — keep polling, do not let it trigger stall detection
                log.debug("transient capture error in poll loop: %s", poll_err)
                last_change_time = time.monotonic()
                continue

            current_count = len(PS1_PATTERN.findall(screen))

            if current_count > initial_count:
                output, exit_code, cwd = _extract_output(screen, command)
                log.info("Command completed: exit=%s cwd=%s [%s]", exit_code, cwd, command[:50])
                self._clear_screen()
                result = _truncate(output).strip()
                hint = _interpret_exit_code(exit_code)
                if not result:
                    result = f"[Command completed with no output. Exit code: {exit_code}{hint}]"
                elif exit_code != 0:
                    result += f"\n[Exit code: {exit_code}{hint}]"
                if cwd:
                    result += f"\n[cwd: {cwd}]"
                return result

            # Size watchdog: kill commands producing excessive output
            if len(screen) > SIZE_WATCHDOG_CHARS:
                log.warning(
                    "Size watchdog triggered (%d chars) — killing session [%s]",
                    len(screen),
                    command[:50],
                )
                try:
                    self._docker_tmux(["send-keys", "-t", self.session, "C-c"])
                except RuntimeError:
                    pass
                output = _extract_interactive_output(screen, baseline)
                return (
                    f"{_truncate(output).strip()}\n\n"
                    f"[SIZE LIMIT] Output exceeded {SIZE_WATCHDOG_CHARS // 1_000_000}M chars. "
                    f"Command interrupted.\n"
                    f"Redirect output to a file: command > /workspace/output.txt"
                )

            # Stall detection: if screen changed from baseline (program produced
            # output) but hasn't changed for STALL_SECONDS, the program is likely
            # waiting for input (interactive prompt like msf6>, sliver>).
            if screen != prev_screen:
                last_change_time = time.monotonic()
                prev_screen = screen
            elif screen != baseline and time.monotonic() - last_change_time >= STALL_SECONDS:
                log.info(
                    "Stall detected after %.1fs — interactive program [%s]",
                    time.monotonic() - start,
                    command[:50],
                )
                output = _extract_interactive_output(screen, baseline)
                return (
                    f"{_truncate(output).strip()}\n"
                    f"[session: {self.session} — interactive, "
                    f"send next command with is_input=True]"
                )

        # Full timeout — include screen capture
        try:
            final_screen = self._capture()
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            final_screen = ""
        screen_tail = final_screen.strip().split("\n")[-20:]
        screen_preview = "\n".join(screen_tail)

        return (
            f"[TIMEOUT] Command exceeded {timeout}s limit.\n"
            f"Session '{self.session}' is still running. "
            f'Send input with bash(command="<input>", is_input=True, session="{self.session}").\n'
            f'Read partial output with bash_output(session="{self.session}").\n'
            f"--- screen preview ---\n{screen_preview}"
        )

    async def execute_async(
        self,
        command: str,
        is_input: bool,
        timeout: int,
        on_auto_background: Callable[[str, str], None] | None = None,
    ) -> str:
        """Async version of execute() — non-blocking subprocess + cancellable polling.

        All subprocess calls are offloaded via asyncio.to_thread() to avoid blocking
        the ASGI event loop. asyncio.sleep() between polls allows CancelledError
        delivery when LangGraph cancels a run (Ctrl+C → cancelMany).

        Args:
            command: shell command to send (or empty / control sequence with is_input).
            is_input: True when ``command`` is keystrokes for an already-running process.
            timeout: max seconds to wait for command completion.
            on_auto_background: optional callback ``(command, baseline) -> None`` invoked
                exactly once when the auto-background threshold is crossed. ``baseline``
                is the screen capture taken before the command was sent — callers use it
                to derive a stable PS1-marker baseline (e.g. via PS1_PATTERN.findall).
        """
        if not is_input:
            await asyncio.to_thread(self.initialize)

        try:
            baseline = await asyncio.to_thread(self._capture)
        except RuntimeError as e:
            error_msg = str(e)
            if "no server running" in error_msg or "session not found" in error_msg:
                log.warning("Session '%s' is dead — attempting recovery", self.session)
                with TmuxSessionManager._init_lock:
                    TmuxSessionManager._initialized.discard(self.session)
                try:
                    await asyncio.to_thread(self.initialize)
                    baseline = await asyncio.to_thread(self._capture)
                except (RuntimeError, OSError, subprocess.TimeoutExpired) as retry_err:
                    return (
                        f"[ERROR] Session recovery failed: {retry_err}\n"
                        f"The tmux session was destroyed or docker is overloaded. "
                        f"Try using a different session name."
                    )
            else:
                return f"[ERROR] Sandbox error: {e}"
        except (OSError, subprocess.TimeoutExpired) as e:
            return (
                f"[ERROR] Sandbox capture failed: {e}\n"
                f"docker exec timed out or the tmux session is hung. "
                f'Retry, or terminate with bash_kill(session="{self.session}").'
            )

        initial_count = len(PS1_PATTERN.findall(baseline))

        if command:
            if is_input:
                if command in ("C-c", "C-z", "C-d"):
                    await asyncio.to_thread(
                        self._docker_tmux, ["send-keys", "-t", self.session, command]
                    )
                else:
                    await asyncio.to_thread(self._send, command, True)
            else:
                await asyncio.to_thread(self._send, command, True)

        start = time.monotonic()
        prev_screen = baseline
        last_change_time = start

        while time.monotonic() - start < timeout:
            await asyncio.sleep(POLL_INTERVAL)  # CancelledError delivered here
            try:
                screen = await asyncio.to_thread(self._capture)
            except RuntimeError as poll_err:
                if "no server running" in str(poll_err):
                    with TmuxSessionManager._init_lock:
                        TmuxSessionManager._initialized.discard(self.session)
                    return (
                        f"[ERROR] tmux session '{self.session}' was destroyed mid-command.\n"
                        f"The command likely killed the shell process (e.g. pkill bash).\n"
                        f"Session will auto-recover on next bash() call."
                    )
                # Other RuntimeError — keep polling, reset stall timer
                log.debug("transient RuntimeError in poll loop: %s", poll_err)
                last_change_time = time.monotonic()
                continue
            except (OSError, subprocess.TimeoutExpired) as poll_err:
                # docker exec stall — keep polling, do not let it trigger stall detection
                log.debug("transient capture error in poll loop: %s", poll_err)
                last_change_time = time.monotonic()
                continue

            current_count = len(PS1_PATTERN.findall(screen))

            if current_count > initial_count:
                output, exit_code, cwd = _extract_output(screen, command)
                log.info("Command completed: exit=%s cwd=%s [%s]", exit_code, cwd, command[:50])
                await asyncio.to_thread(self._clear_screen)
                result = _truncate(output).strip()
                hint = _interpret_exit_code(exit_code)
                if not result:
                    result = f"[Command completed with no output. Exit code: {exit_code}{hint}]"
                elif exit_code != 0:
                    result += f"\n[Exit code: {exit_code}{hint}]"
                if cwd:
                    result += f"\n[cwd: {cwd}]"
                return result

            # Size watchdog: kill commands producing excessive output
            if len(screen) > SIZE_WATCHDOG_CHARS:
                log.warning(
                    "Size watchdog triggered (%d chars) — killing session [%s]",
                    len(screen),
                    command[:50],
                )
                try:
                    await asyncio.to_thread(
                        self._docker_tmux, ["send-keys", "-t", self.session, "C-c"]
                    )
                except RuntimeError:
                    pass
                output = _extract_interactive_output(screen, baseline)
                return (
                    f"{_truncate(output).strip()}\n\n"
                    f"[SIZE LIMIT] Output exceeded {SIZE_WATCHDOG_CHARS // 1_000_000}M chars. "
                    f"Command interrupted.\n"
                    f"Redirect output to a file: command > /workspace/output.txt"
                )

            # Auto-background: convert blocking commands after threshold
            elapsed = time.monotonic() - start
            if elapsed >= AUTO_BACKGROUND_SECONDS and command:
                log.info(
                    "Auto-backgrounding after %.0fs [%s] in session '%s'",
                    elapsed,
                    command[:50],
                    self.session,
                )
                if on_auto_background is not None:
                    try:
                        on_auto_background(command, baseline)
                    except Exception:
                        log.exception("auto-background callback failed")
                output = _extract_interactive_output(screen, baseline)
                preview = _truncate(output).strip()
                return (
                    f"[AUTO-BACKGROUND] Command running >{int(AUTO_BACKGROUND_SECONDS)}s "
                    f"in session '{self.session}'.\n"
                    f"--- partial output ---\n{preview[-1000:] if preview else '(no output yet)'}\n"
                    f"--- end ---\n"
                    f"You will be notified when it completes. Inspect early progress: "
                    f'bash_output(session="{self.session}").'
                )

            # Stall detection (see sync execute() for rationale)
            if screen != prev_screen:
                last_change_time = time.monotonic()
                prev_screen = screen
            elif screen != baseline and time.monotonic() - last_change_time >= STALL_SECONDS:
                log.info(
                    "Stall detected after %.1fs — interactive program [%s]",
                    time.monotonic() - start,
                    command[:50],
                )
                output = _extract_interactive_output(screen, baseline)
                return (
                    f"{_truncate(output).strip()}\n"
                    f"[session: {self.session} — interactive, "
                    f"send next command with is_input=True]"
                )

        # Full timeout — include screen capture
        try:
            final_screen = await asyncio.to_thread(self._capture)
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            final_screen = ""
        screen_tail = final_screen.strip().split("\n")[-20:]
        screen_preview = "\n".join(screen_tail)

        return (
            f"[TIMEOUT] Command exceeded {timeout}s limit.\n"
            f"Session '{self.session}' is still running. "
            f'Send input with bash(command="<input>", is_input=True, session="{self.session}").\n'
            f'Read partial output with bash_output(session="{self.session}").\n'
            f"--- screen preview ---\n{screen_preview}"
        )

    def read_screen(self) -> str:
        """Read current screen without sending any command."""
        try:
            self.initialize()
            screen = self._capture()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            return (
                f"[ERROR] Could not read screen for session '{self.session}': {e}\n"
                f"The tmux session may be hung or docker is overloaded. "
                f'Retry, or terminate the session with bash_kill(session="{self.session}").'
            )
        matches = list(PS1_PATTERN.finditer(screen))
        if matches:
            last = matches[-1]
            exit_code = int(last.group(1))
            cwd = last.group(2)
            recent = screen[last.end() :].strip()
            if recent:
                return f"[RUNNING] cwd={cwd}\n{_truncate(recent)}"
            return f"[IDLE] exit_code={exit_code} cwd={cwd}\nSession is ready for commands."
        return f"[UNKNOWN]\n{screen[-2000:]}"


# ─── Output helpers (transplanted from tools/bash/tool.py) ───────────────


def _extract_interactive_output(screen: str, baseline: str) -> str:
    """Extract new output from an interactive program (no PS1 marker).

    Compares the current screen against the baseline to find new content
    produced by the interactive program since the command was sent.
    """
    # Find the PS1 marker in the baseline — everything after it is new
    matches = list(PS1_PATTERN.finditer(baseline))
    if matches:
        last = matches[-1]
        new_content = screen[last.end() :].strip()
        return new_content if new_content else screen.strip()
    # No PS1 in baseline either — return the diff
    baseline_lines = set(baseline.strip().split("\n"))
    screen_lines = screen.strip().split("\n")
    new_lines = [ln for ln in screen_lines if ln not in baseline_lines]
    return "\n".join(new_lines) if new_lines else screen.strip()


def _extract_output(screen: str, command: str) -> tuple[str, int, str]:
    matches = list(PS1_PATTERN.finditer(screen))
    if not matches:
        return screen, -1, ""
    last = matches[-1]
    exit_code = int(last.group(1))
    cwd = last.group(2)
    if len(matches) >= 2:
        raw = screen[matches[-2].end() : last.start()]
    else:
        raw = screen[: last.start()]
    lines = raw.strip().split("\n")
    if lines and command and lines[0].strip().endswith(command.strip()):
        lines = lines[1:]
    return "\n".join(lines).strip(), exit_code, cwd


def _truncate(text: str) -> str:
    """Truncate large outputs preserving head + tail for context efficiency.

    Observation masking: large tool outputs are the #1 context consumer.
    Keep the first and last portions (highest signal) and summarize the middle.
    """
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    # Asymmetric split: more head (often contains headers/structure) than tail
    head_chars = int(MAX_OUTPUT_CHARS * 0.6)
    tail_chars = MAX_OUTPUT_CHARS - head_chars
    mid_text = text[head_chars:-tail_chars]
    mid_lines = mid_text.count("\n")
    mid_chars = len(mid_text)
    return (
        f"{text[:head_chars]}\n\n"
        f"[... {mid_lines} lines / {mid_chars} chars truncated — "
        f"save full output to file with -oN or redirect (> /workspace/output.txt) "
        f"to preserve complete results ...]\n\n"
        f"{text[-tail_chars:]}"
    )


# ─── Background job tracking ─────────────────────────────────────────────


@dataclasses.dataclass
class BackgroundJob:
    """Metadata for one background command in a tmux session.

    A session holds at most one BackgroundJob — sequential reuse replaces.
    Timestamps use ``time.monotonic()`` so elapsed values stay correct
    across wall-clock adjustments (NTP step, manual ``date -s``).
    """

    session: str
    command: str
    initial_markers: int
    started_at: float
    status: str = "running"  # running | done
    exit_code: int | None = None
    completed_at: float | None = None
    consumed: bool = False

    @property
    def elapsed(self) -> float:
        end = self.completed_at if self.completed_at is not None else time.monotonic()
        return end - self.started_at


class BackgroundJobTracker:
    """In-memory background-job registry keyed by session name."""

    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = threading.RLock()

    def register(self, session: str, command: str, initial_markers: int) -> BackgroundJob:
        with self._lock:
            job = BackgroundJob(
                session=session,
                command=command,
                initial_markers=initial_markers,
                started_at=time.monotonic(),
            )
            self._jobs[session] = job
            return job

    def get(self, session: str) -> BackgroundJob | None:
        with self._lock:
            return self._jobs.get(session)

    def mark_complete(self, session: str, exit_code: int) -> None:
        with self._lock:
            job = self._jobs.get(session)
            if job is None or job.status != "running":
                return
            job.status = "done"
            job.exit_code = exit_code
            job.completed_at = time.monotonic()

    def mark_consumed(self, session: str) -> None:
        with self._lock:
            job = self._jobs.get(session)
            if job is not None:
                job.consumed = True

    def pending_completions(self) -> list[BackgroundJob]:
        with self._lock:
            return [j for j in self._jobs.values() if j.status == "done" and not j.consumed]

    def all_jobs(self) -> list[BackgroundJob]:
        with self._lock:
            return list(self._jobs.values())

    def remove(self, session: str) -> None:
        with self._lock:
            self._jobs.pop(session, None)


# ─── DockerSandbox ────────────────────────────────────────────────────────


class DockerSandbox(BaseSandbox):
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
    ) -> None:
        self._container_name = container_name
        self._default_timeout = default_timeout
        self._managers: dict[str, TmuxSessionManager] = {}
        self._managers_lock = threading.RLock()

    def _get_manager(self, session: str) -> TmuxSessionManager:
        with self._managers_lock:
            if session not in self._managers:
                self._managers[session] = TmuxSessionManager(session, self._container_name)
            return self._managers[session]

    # ── BaseSandbox abstract methods ──────────────────────────────────────

    @property
    def id(self) -> str:
        return self._container_name

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Simple docker exec — used by BaseSandbox for file operations."""
        effective = timeout if timeout is not None else self._default_timeout
        try:
            result = subprocess.run(
                ["docker", "exec", self._container_name, "sh", "-c", command],
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

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    ["docker", "cp", tmp_path, f"{self._container_name}:{path}"],
                    capture_output=True,
                )
                error = None if result.returncode == 0 else "file_not_found"
            finally:
                os.unlink(tmp_path)
            responses.append(FileUploadResponse(path=path, error=error))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            result = subprocess.run(
                ["docker", "cp", f"{self._container_name}:{path}", "-"],
                capture_output=True,
            )
            if result.returncode != 0:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            try:
                with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
                    member = tar.getmembers()[0]
                    f = tar.extractfile(member)
                    file_bytes = f.read() if f else b""
                responses.append(FileDownloadResponse(path=path, content=file_bytes, error=None))
            except Exception:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses

    def read_session_log_diff(self, session: str) -> str:
        """Return new bytes appended to /workspace/.sessions/<session>.log
        since the previous call (or the whole file on first call).

        Per-process offset tracking only — restart resets to 0 (safe fallback).
        File truncation/rotation also resets to 0.
        """
        log_path = f"/workspace/.sessions/{session}.log"
        results = self.download_files([log_path])
        if not results or results[0].error or results[0].content is None:
            return ""
        full = results[0].content
        with self._log_offsets_lock:
            prev_offset = self._log_offsets.get(session, 0)
            if prev_offset > len(full):
                prev_offset = 0
            new_bytes = full[prev_offset:]
            self._log_offsets[session] = len(full)
        return new_bytes.decode("utf-8", errors="replace")

    def reset_session_log_offset(self, session: str) -> None:
        """Forget the read offset (used after kill / GC)."""
        with self._log_offsets_lock:
            self._log_offsets.pop(session, None)

    # ── Tmux execution (for bash tool) ───────────────────────────────────

    def execute_tmux(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
    ) -> str:
        """Tmux-based execution with session persistence and interactive support.

        Used exclusively by the bash tool. Supports:
        - Named sessions for parallel command execution
        - Interactive input (y/n, passwords, C-c / C-z / C-d)
        - Output truncation for large outputs
        """
        effective = timeout if timeout is not None else self._default_timeout
        mgr = self._get_manager(session)

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
    ) -> str:
        """Async tmux execution — cancellable via asyncio.CancelledError.

        Used by the async bash tool so that LangGraph run cancellation
        (Ctrl+C → cancelMany) interrupts the polling loop promptly.
        """
        effective = timeout if timeout is not None else self._default_timeout
        mgr = self._get_manager(session)

        if not command and not is_input:
            return await asyncio.to_thread(mgr.read_screen)

        def _on_auto_background(cmd: str, baseline: str) -> None:
            self._jobs.register(
                session,
                command=cmd,
                initial_markers=len(PS1_PATTERN.findall(baseline)),
            )

        return await mgr.execute_async(
            command,
            is_input=is_input,
            timeout=effective,
            on_auto_background=_on_auto_background,
        )

    def start_background(self, command: str, session: str = "main") -> None:
        """Launch a command in a named tmux session without blocking.

        Registers a BackgroundJob keyed by the PS1-marker count at launch;
        ``poll_completion`` later compares against this baseline.
        """
        mgr = self._get_manager(session)
        mgr.initialize()
        baseline = mgr._capture()
        initial_markers = len(PS1_PATTERN.findall(baseline))
        self._jobs.register(session, command=command, initial_markers=initial_markers)
        mgr._send(command, enter=True)

    def poll_completion(self, session: str) -> "BackgroundJob | None":
        """Check whether a background job has produced a new PS1 marker.

        Updates the tracker in place; returns the job (or None if not tracked).
        Capture failures are swallowed — the job stays running, retried later.
        """
        job = self._jobs.get(session)
        if job is None or job.status != "running":
            return job
        try:
            mgr = self._get_manager(session)
            screen = mgr._capture()
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            return job
        markers = list(PS1_PATTERN.finditer(screen))
        if len(markers) > job.initial_markers:
            try:
                exit_code = int(markers[-1].group(1))
            except ValueError:
                exit_code = -1
            self._jobs.mark_complete(session, exit_code=exit_code)
        return job

    def kill_session(self, session: str) -> None:
        """Send Ctrl+C, then kill the tmux session, then clear all caches.

        Best-effort: errors are logged, not raised. The pipe-pane log file
        is preserved at /workspace/.sessions/<session>.log for audit.
        """
        try:
            mgr = self._get_manager(session)
            try:
                mgr._docker_tmux(["send-keys", "-t", session, "C-c"])
            except RuntimeError as e:
                log.debug("send-keys C-c failed for '%s': %s", session, e)
            try:
                mgr._docker_tmux(["kill-session", "-t", session])
            except RuntimeError as e:
                log.warning("kill-session failed for '%s': %s", session, e)
        finally:
            with self._managers_lock:
                self._managers.pop(session, None)
            with TmuxSessionManager._init_lock:
                TmuxSessionManager._initialized.discard(session)
            self.reset_session_log_offset(session)
            self._jobs.remove(session)


# ─── Pre-flight check ────────────────────────────────────────────────────


def check_sandbox_running(container_name: str = "decepticon-sandbox") -> bool:
    """Check if the Docker sandbox container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False
