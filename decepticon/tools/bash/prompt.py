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
Working directory, environment variables, and background jobs persist
across calls within the same session name. The session starts in the
active engagement workspace supplied by the launcher.

### bash() — execute a command

```
bash(command, session="main", background=False, timeout=120, is_input=False, description="")
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `command` | `""` | Shell command. Empty = read current screen |
| `session` | `"main"` | Different names = parallel sessions. Use a dedicated name for background jobs |
| `background` | `False` | Start without waiting. Returns `[BACKGROUND]` immediately |
| `timeout` | `120` | Max seconds to wait. Commands running >60s auto-background |
| `is_input` | `False` | True ONLY when sending input to a waiting interactive process |
| `description` | `""` | Short UI label |

Return-value markers from `bash()`:
- normal output (single PS1 cycle, ≤15K chars) — command finished, returned inline
- `[BACKGROUND]` — `background=True` accepted; job tracking started
- `[AUTO-BACKGROUND]` — command exceeded 60s and was auto-converted; partial output preview included
- `[SIZE LIMIT]` — output exceeded 5M chars; command was interrupted; redirect to file
- `[TIMEOUT]` — `timeout` reached; session still occupied (use a different session for new commands; check this one with `bash_output`)
- `[session: <name> — interactive, send next command with is_input=True]` — interactive prompt detected (msf, sliver, REPL)
- `[ERROR]` — sandbox/tmux failure; message explains; retry or `bash_kill`

### bash_output(session="main") — fetch new output / completion status

Returns the diff since the last call PLUS one of:
- `[RUNNING elapsed=Ts]` — still working
- `[DONE exit=N elapsed=Ts]` — completed; details delivered ONCE then marked consumed
- `[IDLE]` — no background job in this session (also after `bash_kill`)

You ALSO receive automatic `<system-reminder>` notifications at the
start of the next turn after a background job finishes. Notifications
fire EXACTLY ONCE per completed session. **When a reminder appears,
call `bash_output(session=)` to retrieve full results and apply them
to your work** — ignoring it leaves the lifecycle in a half-state. You
do NOT need to poll bash_output every turn; it is for explicit fetch
when you decide to look or after seeing a reminder.

### bash_status() — list known sessions

Use before launching a new background job (spot conflicts) or to
find stale sessions. Returns a table:
```
session | status                | elapsed | command
--------+-----------------------+---------+--------
<name>  | running               | 12.3s   | <command>
<name>  | done(exit=0) consumed | 25.0s   | <command>
```

### bash_kill(session) — terminate a session

Sends Ctrl+C, tears down the tmux session, removes the job from the
tracker, and clears local state. The pipe-pane log is preserved under
the active engagement workspace's `.sessions/` directory. Returns:
```
[KILLED] session '<name>' terminated. Log preserved at <workspace>/.sessions/<name>.log.
```
Subsequent `bash_output(session=<name>)` returns `[IDLE]`.

## Background Job Lifecycle

```
bash(..., background=True)            ┐
  └─ or bash(...) running >60s        ├─ status=running, tracker registered
                                      ┘
        ↓ (PS1 marker appears in pane)
  poll_completion (each turn) detects → status=done

        ↓ (next turn's before_model)
  <system-reminder> emitted ONCE in agent's message stream

        ↓ (you call bash_output)
  full results returned, status=consumed

        ↓ (you call bash_kill, optional)
  job removed from tracker, session torn down, log preserved
```

## Working Directory & Session State

The session starts at the active engagement workspace. After one `cd recon`, every
subsequent `bash(..., session="main")` runs in `recon/` — do NOT
re-prefix every command with repeated absolute workspace paths. Different
sessions have INDEPENDENT cwd.

## Parallel Workflow

Use a dedicated session for each long-running command. Keep `main`
free for ad-hoc foreground checks while a heavy scan runs:
```
bash(command="nmap -sV --top-ports 1000 target", session="nmap", background=True)
bash(command="dig target", session="main")
bash(command="curl -sI target", session="main")
# ... continue work — you'll be notified when nmap finishes
```

## Output Management

| Output Size | Behavior |
|-------------|----------|
| ≤15K chars | Returned inline |
| >15K chars | Auto-saved to the active engagement workspace's `.scratch/`, preview + path returned |
| >5M chars | Command killed (size watchdog). Redirect to a file: `command > /workspace/output.txt` |

ANSI codes stripped, repetitive lines compressed.

## Interactive Programs (msfconsole, sliver, evil-winrm, REPLs)

The tool auto-detects waiting prompts:
```
bash(command="sliver-client console", session="c2")
bash(command="https -l 443", is_input=True, session="c2")
bash(command="C-c", is_input=True, session="c2")  # Ctrl+C
```

NEVER start with `is_input=True`. NEVER use `nohup ... &` — use named
sessions and `background=True` instead.

## Exit Code Hints

- `127` — command not found → `apt-get install -y <pkg>`
- `130` — interrupted by Ctrl+C
- `137` — killed (OOM or size limit) → redirect output to a file
- `143` — terminated externally

## File Creation

ALWAYS use `write_file` for file creation. NEVER `cat > file << EOF` —
it echoes content back as tool output and wastes context.

## Raw-Socket / Long-Running Probe Discipline

Raw-socket probes (HTTP request smuggling, custom protocol fuzzers, bespoke TLS
handshakes) are the most common silent-stall surface in this sandbox —
`socket.recv()` defaults to BLOCKING FOREVER. Treat every raw-socket script as
untrusted until the rules below hold.

| Rule | Why |
|------|-----|
| `sock.settimeout(5)` BEFORE `connect` AND BEFORE EACH `recv` | `socket.create_connection(timeout=...)` covers connect only; recv blocks forever without `settimeout` after. |
| Outer wall: `timeout 60 python3 -u -c '...'` even when inner timeouts are set | Inner timeout can lose to a kernel wedge or buffered TLS state. Hard wall is mandatory. |
| `python3 -u` (or `sys.stdout.flush()` after each write) | Without `-u`, a wedged process leaves stdout buffered — looks like "no output" when the script is actually finishing. |
| Bounded iteration — break on empty `recv`, or after N bytes / N rounds | `while True: data = s.recv(4096)` against a keep-alive socket never terminates. |
| Prefer inline `python3 -c` over `cat > script.py && python3 script.py` | Inline keeps the harness in the tool transcript and avoids re-creating files between calls. |

## Wedged-Session Recovery

Symptom: `bash_status()` shows session as `running` for >90s past expected completion AND `bash_output(session=...)` returns empty diffs across two consecutive checks.

1. Check `bash_status()` — confirm `running` not `done(...) consumed`.
2. `bash_kill(session=<wedged>)` — tears down tmux, preserves the session log under `.sessions/` for forensics.
3. Open a fresh session under a NEW name (e.g. `<orig>_retry`) — do NOT reuse the killed session name in the same turn (race with cleanup).
4. Re-launch with both `sock.settimeout(5)` AND `timeout 60` outer wall.

## Background Job Budget

Any single bash command running >5 min wall-clock with no observable progress
output should be `bash_kill`'d and the strategy reconsidered. Long-running ops
(nmap full port sweep, ffuf large wordlist) belong in `background=True` named
sessions while you continue work on `main`.

For credential brute-force specifically: cap at 5 minutes OR 1000 attempts,
whichever first. If those fail, the challenge design is not "brute it"; pivot.
</BASH_TOOLS>"""
