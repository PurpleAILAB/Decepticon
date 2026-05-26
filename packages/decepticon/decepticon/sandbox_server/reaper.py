"""SIGCHLD reaper for the sandbox daemon.

The daemon spawns many short-lived child processes — every ``tmux``
subcommand, every ``sh -c`` for ``execute()``, every ``mkdir`` for
``pipe-pane`` setup. Most of these are run through
``subprocess.run(...)`` which waits on its child, but the tmux server
itself, the bash shells launched by ``tmux new-session``, and any
shell-spawned grandchildren are **not** waited on by the daemon — the
parent of those grandchildren (the tmux server) reaps them, but when
the tmux server itself exits its children get reparented to PID 1
(the daemon) and the daemon never calls ``waitpid`` on them.

Without a SIGCHLD handler those reparented children become zombies
that linger until the daemon process exits. A long-running engagement
session was observed accumulating four ``<defunct>`` ``tmux``/``bash``
processes; under sustained use the kernel's per-process PID table
fills up and ``fork()`` starts failing with EAGAIN.

The fix is the standard Unix pattern: install one SIGCHLD handler at
startup that loops ``os.waitpid(-1, os.WNOHANG)`` until no more exited
children remain. The handler is reentrant-safe — ``os.waitpid`` is an
async-signal-safe syscall wrapper and we do no allocation in the
signal frame beyond what the CPython signal machinery already does.

Placement: installed from the FastAPI ``lifespan`` startup hook so it
covers the entire daemon process lifetime, BEFORE any ``DaemonSandbox``
subprocess is spawned. Tests can import :func:`reap_zombies` and
:func:`install_sigchld_reaper` directly.
"""

from __future__ import annotations

import logging
import os
import signal
from types import FrameType

log = logging.getLogger("decepticon.sandbox_server.reaper")


def reap_zombies(signum: int | None = None, frame: FrameType | None = None) -> int:
    """Drain any exited child processes the kernel is holding for us.

    Loops ``os.waitpid(-1, os.WNOHANG)`` until no more zombies remain.
    Safe to call both as a ``signal.signal`` handler (the ``signum`` /
    ``frame`` args match that contract) and as a plain function from
    tests.

    Returns the number of children reaped — useful for assertions in
    tests and for the debug log line below.
    """
    reaped = 0
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            # No children at all — fully drained.
            break
        if pid == 0:
            # Children exist but none have exited yet.
            break
        reaped += 1
    if reaped:
        log.debug("reaped %d zombie child process(es)", reaped)
    return reaped


def install_sigchld_reaper() -> None:
    """Install :func:`reap_zombies` as the SIGCHLD handler.

    Should be called from the main thread (``signal.signal`` restriction)
    BEFORE any subprocess is spawned. Idempotent — re-installing the
    handler is safe.

    On platforms without SIGCHLD (Windows) this is a no-op; the daemon
    only runs inside the Linux sandbox container in production, but
    keeping the call cross-platform-safe means test runners on macOS /
    Linux dev boxes don't blow up importing the module.

    A ``ValueError`` from ``signal.signal`` ("signal only works in main
    thread of the main interpreter") is downgraded to a warning. In
    production the lifespan startup runs on the main thread so the
    install succeeds; the only path that hits this branch is unit
    tests that spin the FastAPI app inside an anyio worker thread.
    """
    if not hasattr(signal, "SIGCHLD"):
        log.debug("SIGCHLD not available on this platform; reaper not installed")
        return
    try:
        signal.signal(signal.SIGCHLD, reap_zombies)
    except ValueError as e:
        # "signal only works in main thread of the main interpreter" —
        # benign in tests; production lifespan runs on the main thread.
        log.warning("could not install SIGCHLD handler (not main thread): %s", e)
        return
    log.info("SIGCHLD zombie reaper installed")
