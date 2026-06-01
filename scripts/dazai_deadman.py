#!/usr/bin/env python3
"""Decepticon ⇄ dazai dead-man's-switch — tear down the stack when the session dies.

Decepticon runs as a Docker stack (``langgraph``, ``neo4j``, ``postgres``, …).
Its secrets do not live in one host process you can register a PID for — they
live in container memory and in the ``neo4j`` / ``postgres`` volumes, and the
provider API keys live in the host ``.env``. So the dead-man's-switch is not
"SIGKILL a PID"; it is "tear the whole stack down and purge what it leaves
behind".

`dazai <https://github.com/New1Direction/ningen-shikkaku>`_ is a host-side
dead-man's-switch tied to the operator's shell / SSH session: an *armed* dazai
daemon, fed a heartbeat by ``dazai client`` from your engagement shell, wipes
its own locked buffers and self-destructs the moment that heartbeat is lost
(past its grace window).

This sentinel turns that daemon-death into a full engagement teardown. It
watches the daemon's liveness over the daemon's UNIX control socket; the instant
the daemon vanishes — i.e. a session-loss panic fired and committed — it runs::

    docker compose -f <stack>/docker-compose.yml down -v --remove-orphans

stopping every container **and purging the volumes** that hold findings and
credentials, then securely overwrites and removes the host ``.env``.

Fail-safe by construction:

* it arms only *after* confirming the daemon alive at least once, so it can
  never tear down before the engagement has started;
* a missing daemon at startup is "not up yet", not a trigger;
* ``--confirm-checks`` consecutive misses are required, so a momentary socket
  hiccup never nukes the stack;
* a clean ``SIGINT`` / ``SIGTERM`` (you stop the sentinel yourself) exits
  **without** teardown — that is the disarm path.

Run it DETACHED from the session it protects, so it outlives the shell::

    nohup python scripts/dazai_deadman.py --stack-dir . >/tmp/deadman.log 2>&1 &
    disown

or use ``make deadman``. Rehearse first with ``--dry-run``: it logs exactly what
it *would* run and wipe, and touches nothing.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import time
from pathlib import Path
from types import FrameType

# dazai's control protocol: connect to the socket, send "<VERB>\n", read one
# reply line. A live daemon answers "STATUS alive=1 armed=… grace=… registered=…".
_STATUS_TIMEOUT_S = 3.0
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _log(msg: str) -> None:
    """Emit a timestamped line to stderr (stdout is reserved for nothing here,
    but stderr keeps logs out of any pipe a caller might read)."""
    print(f"[dazai-deadman] {msg}", file=sys.stderr, flush=True)


def default_socket_path() -> str:
    """Mirror dazai's default: ``${XDG_RUNTIME_DIR:-/tmp}/dazai-$UID.sock``."""
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(base, f"dazai-{os.getuid()}.sock")


def daemon_alive(sock_path: str) -> bool:
    """True iff an armed dazai daemon answers ``STATUS`` on ``sock_path``.

    Any failure to connect or read (daemon gone, socket removed, connection
    refused, timeout) is reported as *not alive* — that is the death signal.
    """
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(_STATUS_TIMEOUT_S)
            s.connect(sock_path)
            s.sendall(b"STATUS\n")
            data = b""
            while b"\n" not in data:
                chunk = s.recv(256)
                if not chunk:
                    break
                data += chunk
    except OSError:
        return False
    line = data.split(b"\n", 1)[0].decode(errors="replace")
    return "alive=1" in line.split()


def shred_file(path: Path, *, dry_run: bool) -> None:
    """Overwrite ``path`` with random bytes, fsync, then unlink. Best-effort."""
    if not path.exists():
        _log(f"env file {path} not present — nothing to wipe")
        return
    if dry_run:
        _log(f"DRY-RUN would shred + remove {path}")
        return
    try:
        size = path.stat().st_size
        with open(path, "r+b", buffering=0) as fh:
            fh.write(os.urandom(max(size, 1)))
            fh.flush()
            os.fsync(fh.fileno())
        path.unlink()
        _log(f"shredded + removed {path}")
    except OSError as exc:
        _log(f"WARN: could not shred {path}: {exc}")


def teardown(*, stack_dir: Path, compose_file: Path, env_file: Path | None, dry_run: bool) -> None:
    """Purge the engagement: ``compose down -v`` then shred ``.env``."""
    import subprocess  # local import: only needed on the trigger path

    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "down",
        "-v",
        "--remove-orphans",
    ]
    _log("=== SESSION LOST — tearing down Decepticon engagement stack ===")
    if dry_run:
        _log(f"DRY-RUN would run: {' '.join(cmd)}  (cwd={stack_dir})")
    else:
        _log(f"running: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, cwd=stack_dir, check=False)  # noqa: S603
            _log(f"compose down exited {result.returncode}")
        except OSError as exc:
            _log(f"WARN: compose down failed to launch: {exc}")
    if env_file is not None:
        shred_file(env_file, dry_run=dry_run)
    _log("=== teardown complete ===")


class _Stop(Exception):
    """Raised from the signal handler to break the watch loop cleanly."""


def _install_disarm_handlers() -> None:
    def handler(signum: int, _frame: FrameType | None) -> None:
        raise _Stop(signal.Signals(signum).name)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def watch(
    *,
    sock_path: str,
    stack_dir: Path,
    compose_file: Path,
    env_file: Path | None,
    interval: float,
    confirm_checks: int,
    dry_run: bool,
) -> int:
    """Watch the daemon; tear down once it dies after having been seen alive."""
    _install_disarm_handlers()
    _log(
        f"watching dazai daemon at {sock_path} "
        f"(interval={interval}s, confirm={confirm_checks}, "
        f"dry_run={dry_run})"
    )
    _log(f"teardown target: {compose_file}" + (f" + shred {env_file}" if env_file else ""))
    _log("waiting for the daemon to come alive before arming…")

    seen_alive = False
    misses = 0
    try:
        while True:
            if daemon_alive(sock_path):
                if not seen_alive:
                    seen_alive = True
                    _log("daemon ALIVE — sentinel ARMED. teardown will fire if it dies.")
                misses = 0
            elif seen_alive:
                misses += 1
                _log(f"daemon not responding ({misses}/{confirm_checks})")
                if misses >= confirm_checks:
                    teardown(
                        stack_dir=stack_dir,
                        compose_file=compose_file,
                        env_file=env_file,
                        dry_run=dry_run,
                    )
                    return 0
            time.sleep(interval)
    except _Stop as why:
        _log(f"{why} received — DISARMED, exiting without teardown")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dazai_deadman.py",
        description="Tear down the Decepticon stack when the dazai-watched session dies.",
    )
    parser.add_argument(
        "--socket",
        default=default_socket_path(),
        help="dazai daemon control socket (default: ${XDG_RUNTIME_DIR:-/tmp}/dazai-$UID.sock)",
    )
    parser.add_argument(
        "--stack-dir",
        type=Path,
        default=_REPO_ROOT,
        help="directory containing docker-compose.yml (default: repo root)",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=None,
        help="compose file to tear down (default: <stack-dir>/docker-compose.yml)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="host secrets file to shred on teardown (default: <stack-dir>/.env)",
    )
    parser.add_argument(
        "--keep-env",
        action="store_true",
        help="do NOT shred .env on teardown (keep provider keys for the next run)",
    )
    parser.add_argument("--interval", type=float, default=2.0, help="poll interval, seconds")
    parser.add_argument(
        "--confirm-checks",
        type=int,
        default=3,
        help="consecutive missed polls required before teardown (debounce)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="log what would happen; never run compose down or shred anything",
    )
    args = parser.parse_args(argv)

    stack_dir: Path = args.stack_dir.resolve()
    compose_file: Path = (args.compose_file or stack_dir / "docker-compose.yml").resolve()
    env_file: Path | None = None if args.keep_env else (args.env_file or stack_dir / ".env")

    if not compose_file.exists():
        _log(f"ERROR: compose file not found: {compose_file}")
        return 2

    return watch(
        sock_path=args.socket,
        stack_dir=stack_dir,
        compose_file=compose_file,
        env_file=env_file,
        interval=args.interval,
        confirm_checks=max(1, args.confirm_checks),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
