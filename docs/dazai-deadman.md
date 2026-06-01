# Session-bound teardown — the dazai dead-man's-switch

Tie a Decepticon engagement to your shell session: if that session dies — you
log out, the SSH connection drops, the box is seized — the **entire stack is
torn down and the secrets it leaves behind are purged**, automatically, within
seconds.

This integrates [**dazai**](https://github.com/New1Direction/ningen-shikkaku), a
host-side, memory-zeroizing dead-man's-switch, as the liveness oracle. The glue
is one small host script: [`scripts/dazai_deadman.py`](../scripts/dazai_deadman.py).

## Why a teardown, not a PID kill

dazai's native mechanism is "SIGKILL a registered **host** PID when the session
dies." Decepticon doesn't fit that shape:

- it runs as a **Docker stack** (`langgraph`, `neo4j`, `postgres`, `litellm`,
  `web`, `sandbox`, …) — container PIDs live in their own namespace and aren't
  killable by a host daemon;
- the sensitive state isn't in one process — it's in **container memory**, in
  the **`neo4j` / `postgres` volumes** (findings, target data, creds), and in
  the host **`.env`** (provider API keys).

So the dead-man's action is `docker compose down -v` (stop every container **and
purge the volumes**) plus a secure wipe of `.env`. That destroys the live
processes *and* the data-at-rest — which a PID kill would leave on disk.

## How it works

```
your shell ──heartbeat──▶ dazai daemon (armed)        scripts/dazai_deadman.py
  (dazai client)             │  self-destructs when         │  polls daemon STATUS
                             │  the heartbeat is lost        │  daemon gone ⇒ teardown
                             ▼                               ▼
                     wipes its locked buffers      docker compose down -v
                     + exits (past --grace)         + shred .env
```

dazai is the session-liveness engine (heartbeat drop, ping-timeout, panic
signals, grace window, reconnect-cancel — all its logic). The sentinel is a thin
**reactor**: it watches the daemon over the daemon's UNIX control socket and,
the instant the daemon vanishes (a session-loss panic that committed past its
grace window), runs the teardown. dazai's SIGKILL can't be trapped to run
cleanup, so reacting to its death is the correct coupling.

## Setup

**1. Install dazai** (once) and put the `dazai` binary on your `PATH` — see its
[repo](https://github.com/New1Direction/ningen-shikkaku).

**2. Start the Decepticon stack** as usual (`make dogfood`, `make dev`, or the
launcher).

**3. Arm dazai, tied to your engagement shell.** In the shell you'll run the
engagement from:

```bash
dazai daemon --arm --grace 5 --ping-timeout 20   # detached/own terminal
dazai client --interval 5                         # holds the heartbeat for THIS shell
```

**4. Arm the teardown sentinel:**

```bash
make deadman          # detached; survives the shell, logs to /tmp/decepticon-deadman.log
```

That's it. Now if the shell/session dies, dazai self-destructs and the sentinel
tears the stack down and shreds `.env`.

## What gets destroyed on trigger

| Target | Action |
|---|---|
| All Decepticon containers | `docker compose down -v --remove-orphans` |
| `neo4j` + `postgres` volumes (findings, target data, creds) | purged by `-v` |
| Host `.env` (provider API keys) | securely overwritten + removed |

```admonish danger
This is destructive on purpose. Keep your `.env` recoverable (a sealed copy / a
password manager) so the next engagement can re-create it. Pass `--keep-env` to
the script if you want to preserve `.env`.
```

## Safety properties

The sentinel is fail-safe by construction (all verified):

- **Arms only after seeing the daemon alive at least once** — it can't fire
  before the engagement has started; a missing daemon at startup is "not up
  yet," not a trigger.
- **Debounced** — `--confirm-checks` (default 3) consecutive missed polls are
  required before teardown, so a momentary socket hiccup never nukes the stack.
- **Clean disarm** — a `SIGINT` / `SIGTERM` (you stop the sentinel yourself)
  exits **without** teardown. To shut down cleanly: stop the sentinel first
  (`Ctrl-C` or `kill`), *then* tear the stack down on your own terms.

## Rehearse it first

```bash
make deadman-dry      # foreground; logs exactly what it WOULD run/shred, touches nothing
```

Then, in another terminal, kill the dazai daemon to simulate session loss and
watch the dry-run sentinel log the teardown it *would* perform, and exit. Only
arm the real `make deadman` once you've seen the rehearsal behave.

## Options

`python scripts/dazai_deadman.py --help`:

| Flag | Default | Meaning |
|---|---|---|
| `--socket PATH` | `${XDG_RUNTIME_DIR:-/tmp}/dazai-$UID.sock` | dazai daemon control socket |
| `--stack-dir DIR` | repo root | directory containing `docker-compose.yml` |
| `--compose-file F` | `<stack-dir>/docker-compose.yml` | compose file to tear down |
| `--env-file F` | `<stack-dir>/.env` | secrets file to shred |
| `--keep-env` | off | do **not** shred `.env` on teardown |
| `--interval N` | `2.0` | poll interval, seconds |
| `--confirm-checks N` | `3` | consecutive missed polls before teardown |
| `--dry-run` | off | log only; never tear down or shred |

## Limitations

- The sentinel must run **detached** from the session it protects (so it
  outlives the shell). `make deadman` uses `nohup … &`; if you launch the script
  by hand, do the same.
- It tears down on **any** daemon disappearance, including a clean `dazai`
  shutdown — hence the "stop the sentinel first" disarm protocol above.
- It does not protect against an attacker who reads the volumes/`.env` *before*
  the session ends — it bounds the window, it doesn't encrypt data at rest.
  dazai's own [threat model](https://new1direction.github.io/ningen-shikkaku/threat-model.html)
  applies to the host secrets it holds directly.
