# tmux bash tool: per-command env re-sync races the PS1 completion marker

**Date:** 2026-06-12
**Component:** `decepticon/sandbox_kernel/tmux.py` (`TmuxSessionManager`)
**Severity:** high — silently drops command output (data loss, not just a hang)

## Symptom

On an already-established (cached-alive) bash session, network/slow commands
(`whois` chasing registrar referrals, `crt.sh`/`curl`, `subfinder`, `dig ANY`)
returned **only their echoed input plus a stray `export DECEPTICON_SKIP_BOOT=1`
line and a `[cwd:…]` marker** — never the command's real stdout:

```
$ whois semrush.com 2>&1 | head -50
export DECEPTICON_SKIP_BOOT=1
whois semrush.com 2>&1 | head -50
[cwd: /workspace/…]
```

The exact same command run directly in the container
(`docker exec … sh -lc 'whois …'`) works fine, and *fast* commands
(`echo`/`ls`/`head`/`which`) work through the tool — so it is neither the
binary nor the network. Agents (e.g. bug-bounty recon, which is network-heavy)
saw their probes return garbage and flailed.

## Root cause — a PS1-marker race introduced by per-command env re-sync

The bash tool detects command completion by counting `[DCPTN:$?:$PWD]` PS1
markers in the captured pane (`execute()`): it snapshots `baseline`, sends the
command, then polls until `current_count > initial_count` and extracts the
segment between the last two markers (`_extract_output`).

`execute()` calls `initialize()` on every non-input command. For a cached-alive
session `initialize()` called **`_sync_passthrough_env()`**, which sends an
`export DECEPTICON_… HTTP_PROXY=…` line *as its own shell command* — and that
export **produces its own PS1 completion marker**.

The race:

1. cached-alive → `_sync_passthrough_env()` sends `export …` (Enter).
2. `execute()` snapshots `baseline = _capture()` **immediately**, before the
   export's marker lands → `initial_count` excludes it.
3. The user command is sent.
4. The poll loop sees `current_count > initial_count` the moment the **export's**
   marker appears — *not* the user command's.
5. `_extract_output()` runs against the segment ending at the export's marker:
   the user command has only been *echoed*, its output has not appeared yet, so
   the tool returns the `export DECEPTICON_SKIP_BOOT=1` + command echo and
   reports success.

Fast commands happen to win the race (their marker lands within the same poll
tick); slower/network commands lose it deterministically.

`DECEPTICON_SKIP_BOOT` itself is benign — it is the intentional session-init env
(set so `python3` subprocesses skip `decepticon/__init__.py`'s boot). It only
*leaked into output* because the per-command export polluted the pane and the
race surfaced its echo.

## Fix

Do not re-sync passthrough env per command. The passthrough env (proxy vars +
`DECEPTICON_*`) is exported once at session creation and **persists for the life
of the persistent shell**; a cached-alive session is, by construction, one this
manager already created and synced (`_cached_pane_is_alive()` requires
membership in `_initialized`, which is only added after the creation-path sync).
The per-command re-sync was therefore redundant *and* a correctness bug.

```diff
         if cached_alive:
-            self._sync_passthrough_env()
             return
```

## Verification

With the patch, on a cached-alive session:

```
run1: echo established            -> "established\n[cwd: /workspace]"
run2: timeout 15 whois semrush.com | head -12
      -> "Domain Name: SEMRUSH.COM\n   Registry Domain ID: …\n   Registrar: MarkMonitor Inc.\n…\n[cwd: /workspace]"
```

`real whois data: True | SKIP_BOOT leak: False`.

## Note on per-command env changes

If a future need arises to propagate parent-env *changes* mid-session, do it
WITHOUT a marker-producing command — e.g. prepend the export to the user command
(`export …; <cmd>` as one command, one marker), or wait for the export's marker
before snapshotting `baseline`. Re-sending a standalone `export` command per
turn must never reach the marker-count completion detector.
