"""Bash tool for the Decepticon agent.

Thin wrapper around DockerSandbox.execute_tmux(). All tmux session
management and PS1 polling logic lives in decepticon/backends/docker_sandbox.py.

The sandbox instance is injected at agent startup via set_sandbox().

Context engineering: multi-tier output management
-------------------------------------------------
Inspired by Claude Code's bash tool best practices:

1. INLINE (≤15K chars) — returned directly in tool result
2. OFFLOAD (15K–100K chars) — saved to /workspace/.scratch/, summary returned
3. HARD_LIMIT (>5M chars) — size watchdog in sandbox kills the command

Additional post-processing:
- ANSI escape code stripping (saves LLM tokens)
- Repetitive line compression (nmap, nuclei patterns)
- Surrogate character sanitization (UTF-8 safety)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time

from langchain_core.tools import tool

from decepticon.backends.docker_sandbox import DockerSandbox, _interpret_exit_code

log = logging.getLogger("decepticon.tools.bash.bash")

_sandbox: DockerSandbox | None = None

# ─── Output size thresholds ──────────────────────────────────────────────
INLINE_LIMIT = 15_000  # ≤15K chars: return inline; >15K: offload to /workspace/.scratch/
# >5M: size watchdog in docker_sandbox.py kills the command (SIZE_WATCHDOG_CHARS)

# ─── Scratch-file TTL prune (bounds /workspace/.scratch/ growth) ──────────
# Files persist long enough for the agent's grep/read multi-pass workflow,
# then expire so the dir does not grow unboundedly across long engagements.
# Process-level throttle keeps the prune off the hot path of every bash call.
SCRATCH_TTL_MINUTES = 60
SCRATCH_PRUNE_INTERVAL = 600  # seconds between prune attempts (per process)
_last_scratch_prune: float = 0.0

# ─── ANSI escape code pattern ────────────────────────────────────────────
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][AB012]")


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes that waste LLM tokens."""
    return _ANSI_ESCAPE.sub("", text)


def _compress_repetitive_lines(text: str, max_repeat: int = 5) -> str:
    """Compress blocks of repetitive lines from scan tools (nmap, nuclei, etc.).

    When >max_repeat consecutive lines share the same prefix pattern,
    keep the first and last few and summarize the middle.
    """
    lines = text.split("\n")
    if len(lines) <= max_repeat * 2:
        return text

    result: list[str] = []
    i = 0
    while i < len(lines):
        # Extract a "signature" — first 20 chars or up to first dynamic token
        line = lines[i]
        sig = line[:20].strip()

        if not sig:
            result.append(line)
            i += 1
            continue

        # Count consecutive lines with the same signature
        j = i + 1
        while j < len(lines) and lines[j][:20].strip() == sig:
            j += 1

        count = j - i
        if count > max_repeat * 2:
            # Keep first max_repeat + last max_repeat, summarize middle
            for k in range(i, i + max_repeat):
                result.append(lines[k])
            skipped = count - max_repeat * 2
            result.append(f"  [... {skipped} similar lines omitted ...]")
            for k in range(j - max_repeat, j):
                result.append(lines[k])
        else:
            for k in range(i, j):
                result.append(lines[k])

        i = j

    return "\n".join(result)


def _sanitize_output(text: str) -> str:
    """Clean tool output: strip surrogates, ANSI codes, compress repetition.

    Processing pipeline:
    1. Re-encode surrogates (UTF-8 safety)
    2. Strip ANSI escape codes (token savings)
    3. Compress repetitive lines (context efficiency)
    """
    # Step 1: surrogate safety
    text = text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
    # Step 2: strip ANSI
    text = _strip_ansi(text)
    # Step 3: compress repetition
    text = _compress_repetitive_lines(text)
    return text


def set_sandbox(sandbox: DockerSandbox) -> None:
    """Inject the shared DockerSandbox instance (called from recon.py)."""
    global _sandbox
    _sandbox = sandbox


def get_sandbox() -> DockerSandbox | None:
    """Return the current DockerSandbox instance (for wiring progress callbacks)."""
    return _sandbox


async def _prune_old_scratch() -> None:
    """Drop scratch files older than SCRATCH_TTL_MINUTES.

    Throttled to SCRATCH_PRUNE_INTERVAL between attempts so the bash() hot
    path pays for cleanup at most every ~10 minutes per process. Best-effort:
    a failure here must never block the agent's command.
    """
    global _last_scratch_prune
    if _sandbox is None:
        return
    now = time.monotonic()
    if now - _last_scratch_prune < SCRATCH_PRUNE_INTERVAL:
        return
    _last_scratch_prune = now
    try:
        await asyncio.to_thread(
            _sandbox.execute,
            f"find /workspace/.scratch -type f -mmin +{SCRATCH_TTL_MINUTES} "
            "-delete 2>/dev/null || true",
            timeout=5,
        )
    except Exception as e:
        log.warning("scratch prune failed: %s", e)


async def _offload_large_output(output: str, command: str, session: str) -> str:
    """Save large output to scratch file in sandbox, return compact reference.

    Implements the filesystem-context "scratch pad" pattern:
    - Write full output to /workspace/.scratch/ for later retrieval
    - Return preview (head 2K + tail 1K) + file path reference
    - Agent can use read_file or grep to access specific parts later
    """
    assert _sandbox is not None

    # Generate unique filename
    ts = int(time.time())
    cmd_hash = hashlib.md5(command.encode()).hexdigest()[:6]
    filename = f"/workspace/.scratch/{session}_{ts}_{cmd_hash}.txt"

    # Write via upload_files (docker cp) to avoid shell injection from output content
    await asyncio.to_thread(_sandbox.execute, "mkdir -p /workspace/.scratch")
    await asyncio.to_thread(_sandbox.upload_files, [(filename, output.encode("utf-8"))])

    # Build compact summary with generous preview (Claude Code: ~10KB preview)
    line_count = output.count("\n") + 1
    char_count = len(output)
    head_preview = output[:2000].strip()
    tail_preview = output[-1000:].strip()

    return (
        f"{head_preview}\n\n"
        f"[... {line_count} lines / {char_count} chars — full output saved to {filename} ...]\n\n"
        f"...{tail_preview}\n\n"
        f"[Full output: {filename} — use read_file or grep to search specific content]"
    )


@tool
async def bash(
    command: str = "",
    is_input: bool = False,
    session: str = "main",
    timeout: int = 120,
    background: bool = False,
    description: str = "",
) -> str:
    """Execute a bash command in a persistent tmux session inside the Docker sandbox.

    See the <BASH_TOOLS> system-prompt block for tool semantics, return-value
    taxonomy, and exit-code hints — this docstring covers parameters only.

    Args:
        command: Shell command. Leave empty to read current screen output of the session.
        is_input: Set True ONLY when an existing command in this session is waiting
            for input (interactive prompt, password, or control sequence like
            'C-c' / 'C-z' / 'C-d'). Never True when starting a new command.
        session: Tmux session name. Different names run in parallel; same name shares cwd.
        timeout: Max seconds to wait for completion (default 120). Commands exceeding
            60s are auto-backgrounded regardless.
        background: Start a long-running command without waiting. Use a dedicated
            session name (not "main"). Check results later with bash_output.
        description: Short label for UI display.
    """
    if _sandbox is None:
        raise RuntimeError("DockerSandbox not initialized. Call set_sandbox() first.")

    # Best-effort TTL prune of /workspace/.scratch/ (throttled internally)
    await _prune_old_scratch()

    # Background mode: send command and return immediately
    if background and command:
        await asyncio.to_thread(_sandbox.start_background, command=command, session=session)
        return (
            f"[BACKGROUND] Command started in session '{session}'.\n"
            f"Do NOT poll — you will be notified when it completes.\n"
            f"Do productive work NOW (curl/dig/whois on 'main', enumerate other targets, etc).\n"
            f'Inspect early progress with bash_output(session="{session}").'
        )

    result = await _sandbox.execute_tmux_async(
        command=command,
        session=session,
        timeout=timeout,
        is_input=is_input,
    )

    # Sanitize: surrogates → ANSI strip → repetitive line compression
    result = _sanitize_output(result)

    # Multi-tier output management:
    # Tier 1 (≤15K): return inline — fits comfortably in context
    # Tier 2 (>15K): offload to file, return preview + file reference
    # Tier 3 (>5M): handled by size watchdog in docker_sandbox.py (command killed)
    if len(result) > INLINE_LIMIT and not result.startswith("["):
        return await _offload_large_output(result, command, session)

    return result


@tool
async def bash_output(session: str = "main") -> str:
    """Retrieve new output from a sandbox session since the last call.

    WHEN TO USE:
    - After bash(..., background=True) to fetch progress or results.
    - After receiving a <system-reminder> notification that a session completed.
    - To re-read a session you've stepped away from while doing other work.

    RETURNS:
    - "[RUNNING elapsed=Ts] session=... command=...\\n<diff>"
    - "[DONE exit=N elapsed=Ts] session=... command=...\\n<diff>"
      (the DONE line is delivered ONCE — after this call the job is "consumed")
    - "[IDLE] No background job in session 'X'."

    Args:
        session: Session name passed to bash(..., background=True).
    """
    if _sandbox is None:
        raise RuntimeError("DockerSandbox not initialized.")

    job = await asyncio.to_thread(_sandbox.poll_completion, session)
    diff_raw = await asyncio.to_thread(_sandbox.read_session_log_diff, session)
    diff = _sanitize_output(diff_raw) if diff_raw else ""

    if job is None:
        if diff:
            return f"[IDLE] No background job in session '{session}'.\n{diff}"
        return f"[IDLE] No background job in session '{session}'."

    if job.status == "done":
        _sandbox._jobs.mark_consumed(session)
        hint = _interpret_exit_code(job.exit_code) if job.exit_code is not None else ""
        body = diff if diff else "(no new output)"
        return (
            f"[DONE exit={job.exit_code}{hint} elapsed={job.elapsed:.1f}s] "
            f"session='{session}' command='{job.command}'\n{body}"
        )

    body = diff if diff else "(no new output yet)"
    return (
        f"[RUNNING elapsed={job.elapsed:.1f}s] session='{session}' command='{job.command}'\n{body}"
    )


@tool
async def bash_kill(session: str) -> str:
    """Forcefully terminate a sandbox session.

    Sends Ctrl+C, kills the tmux session, and clears local job tracking.
    The pipe-pane log file is preserved at /workspace/.sessions/<session>.log.

    Args:
        session: Session name to terminate.
    """
    if _sandbox is None:
        raise RuntimeError("DockerSandbox not initialized.")

    await asyncio.to_thread(_sandbox.kill_session, session)
    return (
        f"[KILLED] session '{session}' terminated. "
        f"Log preserved at /workspace/.sessions/{session}.log."
    )


@tool
async def bash_status() -> str:
    """List all known sandbox sessions with running and completed jobs.

    Use before launching a new background job to spot conflicts, or to
    detect stale sessions for cleanup.
    """
    if _sandbox is None:
        raise RuntimeError("DockerSandbox not initialized.")

    # Poll all known running jobs first, then take ONE snapshot for the table.
    for job in _sandbox._jobs.all_jobs():
        if job.status == "running":
            await asyncio.to_thread(_sandbox.poll_completion, job.session)

    jobs = _sandbox._jobs.all_jobs()
    if not jobs:
        return "[EMPTY] No tracked background jobs."

    rows = ["session | status | elapsed | command", "--------+--------+---------+--------"]
    for j in jobs:
        if j.status == "running":
            status = "running"
        else:
            status = f"done(exit={j.exit_code})"
            if j.consumed:
                status += " consumed"
        rows.append(f"{j.session} | {status} | {j.elapsed:.1f}s | {j.command[:60]}")
    return "\n".join(rows)
