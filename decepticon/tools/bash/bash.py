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
import re
import time

from langchain_core.tools import tool

from decepticon.backends.docker_sandbox import DockerSandbox

_sandbox: DockerSandbox | None = None

# ─── Multi-tier output thresholds (Claude Code best practice) ─────────────
INLINE_LIMIT = 15_000  # ≤15K chars: return directly in tool result
OFFLOAD_THRESHOLD = 100_000  # 15K–100K: save to file, return summary + preview
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
    except Exception:
        pass


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
    """Execute a bash command inside the isolated Docker sandbox (Kali Linux).

    WHAT: Runs shell commands in a persistent tmux session inside the Docker container.
    Each session maintains state (cwd, env vars, background processes) across calls.
    Long-running commands (>60s) are automatically converted to background mode —
    the agent can continue working and check results later.

    WHEN TO USE:
    - Running recon tools: nmap, dig, whois, subfinder, curl, netcat
    - File operations inside sandbox: cat, ls, grep on /workspace files
    - Installing missing packages: apt-get install -y <pkg>
    - Checking a parallel session: bash(command="", session="scan-1")

    RETURNS:
    - Command output (stdout). On failure, exit code + semantic hint appended
      (e.g., "Exit code: 127 — command not found").
    - For large outputs (>100K chars): auto-saved to /workspace/.scratch/ with
      preview returned. Use read_file or grep to access full content.
    - [BACKGROUND]: Command started in session. Do NOT check immediately — do other work first.
    - [AUTO-BACKGROUND]: Command was running >60s and auto-converted to background.
      Check later with bash(command="", session="<name>").
    - [SIZE LIMIT]: Output exceeded 5M chars; command was interrupted.
      Redirect output to a file: command > /workspace/output.txt
    - [TIMEOUT]: Session is now OCCUPIED. Use a DIFFERENT session for new commands.
    - [IDLE]: Session ready, no running process (when checking a session with empty command).
    - [RUNNING]: Session has active output (when checking a session with empty command).

    ERROR RECOVERY:
    - [TIMEOUT] → Session occupied. Use a different session name for new commands.
      Check the timed-out session later: bash(command="", session="<same>")
    - Exit code 126 → Permission denied. Try with sudo or check file path
    - Exit code 127 → Command not found. Install: apt-get install -y <pkg>
    - Exit code 137 → Process killed (OOM or size limit). Redirect output to file

    Args:
        command: Shell command to execute. Leave empty to read current screen output of the session.
        is_input: ONLY set True when a PREVIOUS command in this session is waiting for input.
            Use for: interactive responses ('y', 'n'), passwords, or control signals ('C-c', 'C-z', 'C-d').
            NEVER set True when starting a new command.
        session: Tmux session name for parallel execution. Example: session="scan-1" and session="scan-2"
            run two scans concurrently. Default "main" for sequential work.
        timeout: Max seconds to wait for command completion (default 120). Increase for long scans.
            Note: commands running >60s may be auto-backgrounded regardless of this value.
        background: Set True to start a long-running command without waiting for completion.
            The command runs in the named session. Check results later with bash(session="<name>").
            ALWAYS use a dedicated session name (not "main") with background=True.
            Example: bash(command="nmap -sV target", session="nmap", background=True)
        description: Short activity description for UI display (e.g., "Scanning target ports").
            Optional — helps operators monitor agent activity in real-time.
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
            f"Do NOT check this session or sleep-wait. Instead, do productive work NOW:\n"
            f"  - Run quick commands (curl, dig, whois) on 'main' session\n"
            f"  - Enumerate services on already-discovered ports\n"
            f"  - Read skill files or analyze existing findings\n"
            f'Check later: bash(command="", session="{session}")'
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
