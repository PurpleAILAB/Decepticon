"""Bash tool prompt — single source for all agents.

Tool documentation lives here. Workflow guidance (when to delegate vs. when
to scan first, what evidence to capture) lives in each agent's persona,
not here — keeping this file focused on tool semantics.
"""

from __future__ import annotations

BASH_PROMPT = """\
<BASH_TOOLS>
## Sandbox Execution Tools

Four tools share persistent tmux sessions inside the Kali sandbox.
Working directory, environment variables, and background jobs persist across
calls within the same session name.

### bash() — execute a command

```
bash(command, session="main", background=False, timeout=120, is_input=False, description="")
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `command` | `""` | Shell command. Empty = read current screen output |
| `session` | `"main"` | Different names = parallel sessions |
| `background` | `False` | Set True for long commands. Use a dedicated session name |
| `timeout` | `120` | Max seconds to wait. Commands running >60s auto-background |
| `is_input` | `False` | Set True ONLY when sending input to a waiting interactive process |
| `description` | `""` | Short label for UI display |

### bash_output(session="main") — fetch new output / completion status

Returns the diff since the last call PLUS one of:
- `[RUNNING elapsed=Ts]` — still working
- `[DONE exit=N elapsed=Ts]` — completed; results delivered ONCE
- `[IDLE]` — no background job in this session

You ALSO receive automatic `<system-reminder>` notifications the next turn
after a background job finishes. You do NOT need to poll bash_output every
turn — it is for explicit fetch when you decide to look.

### bash_kill(session) — terminate a session

Sends Ctrl+C and tears down the tmux session. The pipe-pane log is
preserved at `/workspace/.sessions/<session>.log` for audit.

### bash_status() — list known sessions

Use before launching a new background job to spot conflicts, or to find
stale sessions for cleanup.

## Working Directory & Session State

The session starts at `/workspace/`. After one `cd recon`, every subsequent
`bash(..., session="main")` runs in `recon/` — do NOT re-prefix every command
with `cd /workspace/... && ...`. Different sessions have INDEPENDENT cwd.

## Output Management

| Output Size | Behavior |
|-------------|----------|
| ≤15K chars | Returned inline |
| >15K chars | Auto-saved to `/workspace/.scratch/`, preview + path returned |
| >5M chars | Command killed (size watchdog). Redirect to a file instead |

ANSI codes stripped, repetitive lines compressed.

## Auto-Background

Commands running >60s become background automatically. You receive
`[AUTO-BACKGROUND]` with a partial-output preview. Continue with other work —
you'll be notified when it completes.

## Interactive Programs (msfconsole, sliver, evil-winrm, REPLs)

The tool auto-detects waiting prompts and returns
`[session: <name> — interactive, send next command with is_input=True]`.

```
bash(command="sliver-client console", session="c2")
bash(command="https -l 443", is_input=True, session="c2")
bash(command="C-c", is_input=True, session="c2")  # Ctrl+C
```

NEVER start with `is_input=True`. NEVER use `nohup ... &` — use named
sessions and `background=True` instead.

## Exit Code Hints

- `127` — command not found → `apt-get install -y <pkg>`
- `137` — killed (OOM or size limit) → redirect output to a file
- `143` — terminated externally

## File Creation

ALWAYS use `write_file` for file creation. NEVER `cat > file << EOF` —
it echoes content back as tool output and wastes context.
</BASH_TOOLS>"""


