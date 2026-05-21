"""TmuxSessionManager + execution helpers — shared between DockerSandbox
(agent-side, via `exec_prefix=["docker", "exec", <ctn>]`) and the in-
container HTTP daemon (sandbox-side, via `exec_prefix=[]`).

Extracted from `decepticon/backends/docker_sandbox.py` so the daemon
can import the tmux machinery without pulling in agent-side transport
classes. See `sandbox_kernel/__init__.py` for the layering rationale.

The semantics — PS1 marker parsing, polling cadence, stall detection,
size watchdog, output truncation, auto-background after 60 s — are
unchanged from the docker_sandbox.py original. Only the import site
moved.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import threading
import time
from collections.abc import Callable

log = logging.getLogger("decepticon.sandbox_kernel.tmux")

# ─── Tunable timing constants (patched in tests) ────────────────────────

PS1_PATTERN = re.compile(r"\[DCPTN:(\d+):(.+?)\]")

POLL_INTERVAL: float = 0.5
STALL_SECONDS: float = 3.0
MAX_OUTPUT_CHARS: int = 30_000
AUTO_BACKGROUND_SECONDS: float = 60.0
SIZE_WATCHDOG_CHARS: int = 5_000_000
SIZE_WATCHDOG_INTERVAL: float = 5.0


def _safe_log(value: object) -> str:
    """Escape control chars so user-controlled strings cannot forge log lines.

    The bash tool and session naming both flow caller-supplied text into
    ``log.<level>(...)`` calls. CodeQL's log-injection rule (medium) flags
    every such site because a ``\\n`` in the value can splice a fake log
    line into structured log readers (Cloud Logging, Loki). The fix is
    cheap and applied uniformly; see callers in this file + base.py.
    """
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


class TmuxCommandError(RuntimeError):
    """Raised when a tmux command fails inside the sandbox container."""

    def __init__(self, args: list[str], returncode: int, output: str) -> None:
        self.args_list = args
        self.returncode = returncode
        self.output = output
        super().__init__(output)


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

    def __init__(
        self,
        session: str,
        container_name: str,
        workspace_path: str = "/workspace",
        log_name: str | None = None,
        exec_prefix: list[str] | None = None,
    ) -> None:
        self.session = session
        self._container = container_name
        self._workspace_path = workspace_path.rstrip("/") or "/workspace"
        self._log_name = log_name or session
        self._pane_id: str | None = None
        # When None, default to the existing docker-exec pattern so
        # nothing changes for DockerSandbox callers. The HTTP sandbox
        # daemon (which runs *inside* the sandbox container and talks
        # to the local tmux directly) passes `exec_prefix=[]` so the
        # same TmuxSessionManager logic is reused without spawning a
        # nested docker daemon.
        self._exec_prefix: list[str] = (
            list(exec_prefix) if exec_prefix is not None else ["docker", "exec", container_name]
        )

    # ── docker / tmux helpers ──

    def _docker_tmux(self, args: list[str], timeout: int = 10) -> str:
        """Run a tmux subcommand against the session's target.

        The prefix in `_exec_prefix` is the only thing that distinguishes
        in-container (host-side, via `docker exec`) from inside-container
        (no prefix) execution — every other tmux semantic is identical.
        """
        result = subprocess.run(
            [*self._exec_prefix, "tmux", "-L", self.session, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise TmuxCommandError(args, result.returncode, error_msg)
        return result.stdout

    def _target(self) -> str:
        """Return the stable tmux target for command dispatch."""
        return self.session

    def _forget_cached_state(self) -> None:
        self._pane_id = None
        with TmuxSessionManager._init_lock:
            TmuxSessionManager._initialized.discard(self.session)

    def _resolve_pane_id(self) -> str:
        try:
            return self._docker_tmux(
                ["display-message", "-p", "-t", self.session, "#{pane_id}"],
                timeout=5,
            ).strip()
        except subprocess.TimeoutExpired:
            self._forget_cached_state()
            time.sleep(1.0)
            return self._docker_tmux(
                ["display-message", "-p", "-t", self.session, "#{pane_id}"],
                timeout=10,
            ).strip()

    def _cached_pane_is_alive(self) -> bool:
        if self.session not in TmuxSessionManager._initialized:
            return False
        if self._pane_id is None:
            try:
                self._pane_id = self._resolve_pane_id()
            except (RuntimeError, subprocess.TimeoutExpired):
                self._forget_cached_state()
                return False
        try:
            self._docker_tmux(
                ["display-message", "-p", "-t", self._pane_id, "#{pane_id}"],
                timeout=5,
            )
            return True
        except subprocess.TimeoutExpired:
            self._forget_cached_state()
            time.sleep(1.0)
            try:
                self._docker_tmux(
                    ["display-message", "-p", "-t", self._pane_id, "#{pane_id}"],
                    timeout=10,
                )
                return True
            except (subprocess.TimeoutExpired, RuntimeError):
                raise TmuxCommandError(
                    ["display-message", "-p", "-t", self._pane_id, "#{pane_id}"],
                    -1,
                    "tmux pane probe timed out after retry — sandbox infra fault",
                )
        except RuntimeError:
            return False

    def _send(self, text: str, enter: bool = True) -> None:
        """Send keystrokes using -l (literal) to prevent tmux escaping bugs."""
        target = self._target()
        self._docker_tmux(["send-keys", "-t", target, "-l", text])
        if enter:
            self._docker_tmux(["send-keys", "-t", target, "Enter"])

    def _clear_screen(self) -> None:
        target = self._target()
        try:
            self._docker_tmux(["send-keys", "-t", target, "C-l"])
            time.sleep(0.1)
            self._docker_tmux(["clear-history", "-t", target])
        except (TmuxCommandError, subprocess.TimeoutExpired, OSError) as e:
            log.warning("_clear_screen failed for '%s': %s", target, e)

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
                self._target(),
            ]
        )

    # ── session lifecycle ──

    def initialize(self) -> None:
        """Create session if needed and inject PS1 marker (once per session)."""
        with TmuxSessionManager._init_lock:
            if self._cached_pane_is_alive():
                return
            TmuxSessionManager._initialized.discard(self.session)
            self._pane_id = None

        session_exists = False
        try:
            self._docker_tmux(["has-session", "-t", self.session], timeout=5)
            session_exists = True
        except RuntimeError:
            session_exists = False

        if not session_exists:
            log.info("Creating tmux session: %s", self.session)
            try:
                if self._workspace_path != "/workspace":
                    subprocess.run(
                        [*self._exec_prefix, "mkdir", "-p", self._workspace_path],
                        capture_output=True,
                        timeout=5,
                        check=True,
                    )
                pane_id = self._docker_tmux(
                    [
                        "new-session",
                        "-d",
                        "-s",
                        self.session,
                        "-c",
                        self._workspace_path,
                        "-P",
                        "-F",
                        "#{pane_id}",
                    ]
                ).strip()
                self._pane_id = pane_id or self.session
            except RuntimeError:
                try:
                    self._docker_tmux(["has-session", "-t", self.session], timeout=5)
                    self._pane_id = self._resolve_pane_id()
                    session_exists = True
                    log.debug("Session %s already exists (race), reusing", self.session)
                except RuntimeError:
                    raise
            time.sleep(0.3)
        else:
            self._pane_id = self._resolve_pane_id()

        # Inject PS1 marker + disable PS2 + clear screen
        ps1_cmd = "export PROMPT_COMMAND='export PS1=\"[DCPTN:$?:$PWD] \"'; export PS2=''; clear"
        self._send(ps1_cmd)
        time.sleep(0.5)
        self._clear_screen()
        time.sleep(0.2)

        if not session_exists and self._workspace_path != "/workspace":
            log_path = f"{self._workspace_path}/.sessions/{self._log_name}.log"
            try:
                # Idempotent — the directory is bind-mounted to the host so
                # operators can tail the same file the agent reads. Use
                # the configured exec_prefix instead of a hardcoded
                # ``docker exec`` so this works both when the manager
                # wraps a sibling docker container AND when it runs
                # in-process inside the HTTP sandbox daemon (where
                # exec_prefix is empty and no docker socket is reachable).
                subprocess.run(
                    [*self._exec_prefix, "mkdir", "-p", f"{self._workspace_path}/.sessions"],
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
            log.warning("Session '%s' is not ready — attempting recovery: %s", self.session, e)
            self._forget_cached_state()
            try:
                self.initialize()
                baseline = self._capture()
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as retry_err:
                return (
                    f"[ERROR] Session recovery failed: {retry_err}\n"
                    f"The tmux session was destroyed or docker is overloaded. "
                    f"Try using a different session name."
                )
        except (OSError, subprocess.TimeoutExpired) as e:
            return (
                f"[ERROR] Sandbox capture failed: {e}\n"
                f"docker exec timed out or the tmux session is hung. "
                f'Retry, or terminate with bash_kill(session="{self.session}").'
            )

        initial_count = len(PS1_PATTERN.findall(baseline))

        if command:
            try:
                if is_input:
                    if command in ("C-c", "C-z", "C-d"):
                        self._docker_tmux(["send-keys", "-t", self._target(), command])
                    else:
                        self._send(command, enter=True)
                else:
                    self._send(command, enter=True)
            except RuntimeError as e:
                return f"[ERROR] Could not send command to session '{self.session}': {e}"

        start = time.monotonic()
        prev_screen = baseline
        last_change_time = start

        while time.monotonic() - start < timeout:
            time.sleep(POLL_INTERVAL)
            try:
                screen = self._capture()
            except RuntimeError as poll_err:
                self._forget_cached_state()
                return (
                    f"[ERROR] tmux session '{self.session}' was destroyed mid-command: {poll_err}\n"
                    f"The command likely killed the shell process (e.g. pkill bash).\n"
                    f"Session will auto-recover on next bash() call."
                )
            except (OSError, subprocess.TimeoutExpired) as poll_err:
                # docker exec stall — keep polling, do not let it trigger stall detection
                log.debug("transient capture error in poll loop: %s", poll_err)
                last_change_time = time.monotonic()
                continue

            current_count = len(PS1_PATTERN.findall(screen))

            if current_count > initial_count:
                output, exit_code, cwd = _extract_output(screen, command)
                log.info(
                    "Command completed: exit=%s cwd=%s [%s]",
                    exit_code,
                    _safe_log(cwd),
                    _safe_log(command[:50]),
                )
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
                    _safe_log(command[:50]),
                )
                try:
                    self._docker_tmux(["send-keys", "-t", self._target(), "C-c"])
                except RuntimeError as interrupt_err:
                    log.debug("Failed to interrupt oversized tmux command: %s", interrupt_err)
                output = _extract_interactive_output(screen, baseline)
                return (
                    f"{_truncate(output).strip()}\n\n"
                    f"[SIZE LIMIT] Output exceeded {SIZE_WATCHDOG_CHARS // 1_000_000}M chars. "
                    f"Command interrupted.\n"
                    f"Redirect output to a file: command > {self._workspace_path}/output.txt"
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
                    _safe_log(command[:50]),
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
            log.warning("Session '%s' is not ready — attempting recovery: %s", self.session, e)
            self._forget_cached_state()
            try:
                await asyncio.to_thread(self.initialize)
                baseline = await asyncio.to_thread(self._capture)
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as retry_err:
                return (
                    f"[ERROR] Session recovery failed: {retry_err}\n"
                    f"The tmux session was destroyed or docker is overloaded. "
                    f"Try using a different session name."
                )
        except (OSError, subprocess.TimeoutExpired) as e:
            return (
                f"[ERROR] Sandbox capture failed: {e}\n"
                f"docker exec timed out or the tmux session is hung. "
                f'Retry, or terminate with bash_kill(session="{self.session}").'
            )

        initial_count = len(PS1_PATTERN.findall(baseline))

        if command:
            try:
                if is_input:
                    if command in ("C-c", "C-z", "C-d"):
                        await asyncio.to_thread(
                            self._docker_tmux, ["send-keys", "-t", self._target(), command]
                        )
                    else:
                        await asyncio.to_thread(self._send, command, True)
                else:
                    await asyncio.to_thread(self._send, command, True)
            except RuntimeError as e:
                return f"[ERROR] Could not send command to session '{self.session}': {e}"

        start = time.monotonic()
        prev_screen = baseline
        last_change_time = start

        while time.monotonic() - start < timeout:
            await asyncio.sleep(POLL_INTERVAL)  # CancelledError delivered here
            try:
                screen = await asyncio.to_thread(self._capture)
            except RuntimeError as poll_err:
                self._forget_cached_state()
                return (
                    f"[ERROR] tmux session '{self.session}' was destroyed mid-command: {poll_err}\n"
                    f"The command likely killed the shell process (e.g. pkill bash).\n"
                    f"Session will auto-recover on next bash() call."
                )
            except (OSError, subprocess.TimeoutExpired) as poll_err:
                # docker exec stall — keep polling, do not let it trigger stall detection
                log.debug("transient capture error in poll loop: %s", poll_err)
                last_change_time = time.monotonic()
                continue

            current_count = len(PS1_PATTERN.findall(screen))

            if current_count > initial_count:
                output, exit_code, cwd = _extract_output(screen, command)
                log.info(
                    "Command completed: exit=%s cwd=%s [%s]",
                    exit_code,
                    _safe_log(cwd),
                    _safe_log(command[:50]),
                )
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
                    _safe_log(command[:50]),
                )
                try:
                    await asyncio.to_thread(
                        self._docker_tmux, ["send-keys", "-t", self._target(), "C-c"]
                    )
                except RuntimeError as interrupt_err:
                    log.debug("Failed to interrupt oversized tmux command: %s", interrupt_err)
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
                    _safe_log(command[:50]),
                    _safe_log(self.session),
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
                    _safe_log(command[:50]),
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
        "save full output to file with -oN or redirect to a workspace file "
        f"to preserve complete results ...]\n\n"
        f"{text[-tail_chars:]}"
    )
