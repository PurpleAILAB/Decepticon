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

You receive automatic `<system-reminder>` notifications at the start
of the next turn after a background job finishes — **with the captured
output already inlined**. Each completion fires EXACTLY ONCE. You do
not need to call `bash_output` to retrieve the result; read the
reminder and apply the output to your work. `bash_output` remains
available for explicit re-inspection of a session you have already
seen (it will return `(no new output)` on the consumed completion).

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
  <system-reminder> emitted ONCE with output inlined — status=consumed
  (no need to call bash_output; it is a re-inspect tool from here)

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

## Output Externalization (mandatory for >2KB output)

If a bash command will produce more than ~2KB of output (HTML page, API JSON, file dump, recursive directory listing, multi-host scan), redirect to a file FIRST and then extract only the fragment you need:

```bash
# WRONG — 50KB curl output joins the LLM context, causes summarization slowdown
curl -s "https://target/"

# RIGHT — capture once, extract narrowly
curl -s "https://target/" > /tmp/root.html
grep -iE 'flag|secret|admin|api' /tmp/root.html | head -20
```

**Why this matters**: Each multi-KB tool output forces SummarizationMiddleware to compact context on the NEXT turn — compaction is expensive and disrupts engagement progress. One pre-extraction `grep` fits cleanly; the raw page does not.

**Heuristics for what to extract** (instead of dumping):

| Source | Extract |
|--------|---------|
| HTML page | `grep -E 'href|action|src|name=' page.html | head -30` |
| JSON response | `jq -r '. | keys'` then `jq '.<field>'` for field of interest |
| File dump (`/etc/passwd`, etc.) | `head -20` then `grep` for keywords |
| Multi-host scan output | `awk '/PASS|FAIL|200|500/ {print}'` |
| Recursive `ls`/`find` | pipe to `head -50` always |

**Exception**: If the entire output IS the flag (single line ≤200 bytes), inline it.

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

## Sandbox Bash Anti-patterns

The sandbox bash environment is intentionally restricted. The following
patterns waste a probe (or hang the cycle) and MUST be avoided. Prefer the
`python3` patterns below — they are deterministic, timeout-bounded, and
produce machine-readable output.

| Pattern | Why it's bad |
|---------|--------------|
| `bash <<'EOF' ... EOF` heredocs in tool calls | Often truncated mid-stream, brittle quoting, ambiguous timeout behavior. |
| Trailing `&` to "parallelize" (`curl ... & curl ... & wait`) | Backgrounded jobs detach from the tool's stdout/timeout — silent failures, races nobody can read. |
| `nohup python3 script.py &` | Functionally identical to `&` backgrounding — process detaches, stdout is lost, cannot be timed out by outer wall-clock. Use `timeout N python3 -u -c '...' \\| tee log.txt` or named-session `background=True` instead. |
| Unbounded `sleep`, `nc -l`, `tail -f`, `while true` | Hits the wall-clock and burns the entire cycle; never produces useful output. |
| `timeout 5 bash -c ""` (empty command) | Zero-effect probe, recon-scope-creep tell. |
| Long pipelines without `set -o pipefail` | Failures hide behind the last successful command. |
| Implicit-shell loops over network targets without per-iteration timeout | One slow host blocks all the others. |

## TTY / ANSI Escape Noise

Interactive tools emit ANSI escape codes (`\\x1b[...m`, carriage returns,
progress bars) when stdout is a TTY. In the sandbox these codes land verbatim
in the tool result, polluting grep/parse output and inflating token count.

Rules:
- Always append `--no-color` (or `--color=never`) for tools that support it
  (`sqlmap --no-color`, `nmap --no-color`, `ffuf -no-color`,
  `hydra -o /tmp/out.txt`).
- For tools without a flag, pipe through `cat`: `tool | cat` — redirecting
  stdout breaks the PTY isatty() check and suppresses ANSI codes.
- Prefer explicit `-o /tmp/output.txt` file output for long-running tools;
  read the file afterward rather than capturing ANSI-polluted stdout.
- Never use `script -q -c '...' /dev/null` to force PTY — it re-enables ANSI
  codes and adds an extra layer of timing unpredictability.

## Preferred Pattern — Python Heredoc with Explicit Timeouts

```bash
python3 - <<'PY'
import requests, sys
r = requests.get("https://<TARGET>/path", timeout=5)
print(r.status_code, len(r.content))
PY
```

For parallel work, use `concurrent.futures.ThreadPoolExecutor` (bounded
`max_workers`, every call carries `timeout=5`) instead of bash `&`. For
repeated probes, write a tight `python3 -c` one-liner with an explicit total
wall-clock cap. Every network call MUST set a timeout. Every loop MUST be
bounded.

## Raw-Socket / Long-Running Probe Discipline

Raw-socket probes (HTTP request smuggling, custom protocol fuzzers, bespoke TLS
handshakes) are the most common silent-stall surface in this sandbox —
`socket.recv()` defaults to BLOCKING FOREVER. Treat every raw-socket script as
untrusted until the rules below hold.

| Rule | Why |
|------|-----|
| `sock.settimeout(<bounded>)` BEFORE `connect` AND BEFORE EACH `recv` | `socket.create_connection(timeout=...)` covers connect only; recv blocks forever without `settimeout` after. Specific value lives in the per-skill doc. |
| Outer wall: `timeout <bounded> python3 -u -c '...'` even when inner timeouts are set | Inner timeout can lose to a kernel wedge or buffered TLS state. Hard wall is mandatory; specific value lives in the per-skill doc. |
| `python3 -u` (or `sys.stdout.flush()` after each write) | Without `-u`, a wedged process leaves stdout buffered — looks like "no output" when the script is actually finishing. |
| Bounded iteration — break on empty `recv`, or after N bytes / N rounds | `while True: data = s.recv(4096)` against a keep-alive socket never terminates. |
| Prefer inline `python3 -c` over `cat > script.py && python3 script.py` | Inline keeps the harness in the tool transcript and avoids re-creating files between calls. |
| Bash-session wedge signature: 3+ consecutive empty-command polls | Means the previous tool call wedged the shell. Open a NEW bash session, `pkill -9 -f <script>`, do NOT keep polling the old one — polling a wedged shell will not unwedge it. |

## Wedged-Session Recovery

Symptom: `bash_status()` shows session as `running` past its expected completion AND `bash_output(session=...)` returns empty diffs across consecutive checks (no new bytes since the previous poll).

1. Check `bash_status()` — confirm `running` not `done(...) consumed`.
2. `bash_kill(session=<wedged>)` — tears down tmux, preserves the session log under `.sessions/` for forensics.
3. Open a fresh session under a NEW name (e.g. `<orig>_retry`) — do NOT reuse the killed session name in the same turn (race with cleanup).
4. Re-launch with both `sock.settimeout(5)` AND `timeout 60` outer wall.

## Tmux Pipe Degradation Detector

When a probe is launched in a tmux session and its stdout is redirected to a
file (`python3 detector.py > /tmp/log 2>&1 &`,
`tmux send-keys '... > /tmp/log' Enter`), the tmux pipe between the running
process and the log file can degrade silently — the process keeps running,
`ps` shows the PID alive, but every byte it writes is discarded by the broken
pipe. From the operator side this looks IDENTICAL to "the script is still
working".

Detection signature (all three conditions hold at the same time):
- The script's PID is alive (`ps -p <PID>` returns 0).
- `cat /tmp/log` returns empty bytes across consecutive polls — the file
  has not grown since the previous read.
- The script SHOULD have produced at least one line by now (it has progress
  logging, a banner, a heartbeat, etc.).

If all three hold, the tmux pipe is broken. Do NOT keep waiting — keep waiting
will continue to return empty forever.

Recovery, in order:

1. Open a NEW bash session (e.g. tag it `<challenge>_recovery` so the original
   tmux name does not collide).
2. `pkill -9 -f <script>` AND `rm -f /tmp/log` AND
   `tmux kill-session -t main 2>/dev/null` (the `2>/dev/null` covers the
   no-such-session case so the recovery does not error out before the next
   step).
3. Re-launch the same probe **inline** —
   `timeout 60 python3 -u -c '<inlined harness>' 2>&1 | tee log.txt` —
   bypassing tmux entirely. Inline `python3 -u -c` writes to the tool's
   stdout, which the harness sees directly.
4. If the inline run also produces no output across recovery polls, the
   issue is NOT tmux degradation but a real wedge in the harness itself.
   Escalate via `update_objective(status="blocked", reason="sandbox tmux
   pipe degradation: inline retry also produced no output")`.

## Diagnostic Ladder

| Symptom | Cause | Recovery |
|---------|-------|----------|
| `ps -p <PID>` alive, `/tmp/log` empty across consecutive polls, script has progress logging | Tmux pipe degradation (writes silently dropped) | New session, pkill + rm log + tmux kill-session, switch to inline `timeout <bounded> python3 -u -c '...' \\| tee log.txt`. |
| `ps -p <PID>` dead, `/tmp/log` empty | Process crashed before first flush (likely import error or syntax error) | `python3 -c '<harness>'` directly to surface the traceback (no `&`, no log redirect). Fix syntax, retry. |
| `ps -p <PID>` alive, `/tmp/log` has bytes but stops growing | Network wedge (no `sock.settimeout`, slow-loris peer, or sandbox throttling) | Apply Wedged-Session Recovery above. Add `sock.settimeout(5)` before connect AND each recv. Outer `timeout 60`. |
| 3+ consecutive empty-command polls (`""`, `echo`, `pwd`) on the SAME shell session | The previous tool call wedged the shell stdin/stdout pump | Open a fresh bash session immediately. Polling the wedged shell will not unwedge it. |

## Background Job Discipline

A background command that has stopped producing observable progress
output (no new bytes in its log, no advancing counter, no oracle
responses) should be `bash_kill`'d and the strategy reconsidered.
Continuing to wait reproduces the same negative state. Long-running
ops (nmap full port sweep, ffuf large wordlist) belong in
`background=True` named sessions while you continue work on `main`.

For credential brute-force specifically: default-credential
challenges deliver via the early entries of common wordlists. If
those entries fail, the challenge intent is not "brute it" — pivot
to the next vector class rather than expanding the wordlist or
extending the run.
</BASH_TOOLS>"""
