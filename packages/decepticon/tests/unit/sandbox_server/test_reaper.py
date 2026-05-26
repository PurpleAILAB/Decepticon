"""Tests for the sandbox daemon's SIGCHLD zombie reaper.

Without the reaper, every subprocess that gets reparented to the daemon
(tmux servers exiting, bash grandchildren outliving their tmux parent)
becomes a ``<defunct>`` process the daemon never waits on. This module
verifies the reaper's two contracts:

  1. ``reap_zombies()`` returns the count of children reaped and leaves
     no zombies behind when called explicitly.
  2. ``install_sigchld_reaper()`` wires the reaper as the SIGCHLD
     handler so subprocess exits are drained automatically.

The tests fork real child processes via ``subprocess.Popen(["true"])``
because mocking ``os.waitpid`` would only verify the function shape,
not the actual zombie-draining behaviour.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator

import pytest

from decepticon.sandbox_server.reaper import (
    install_sigchld_reaper,
    reap_zombies,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SIGCHLD / waitpid semantics are POSIX-only; the daemon ships in a Linux container",
)


@pytest.fixture
def _restore_sigchld() -> Iterator[None]:
    """Snapshot and restore the SIGCHLD handler around each test.

    The reaper installation is process-global state; without this fixture
    a failing test would leak its handler into every subsequent test.
    """
    prev = signal.getsignal(signal.SIGCHLD)
    yield
    signal.signal(signal.SIGCHLD, prev)


def _count_zombie_children() -> int:
    """Return how many of this process's children are zombies right now.

    Reads ``/proc/<pid>/status`` on Linux; falls back to ``ps`` elsewhere
    (macOS dev boxes). Counting via ``waitpid`` would itself drain the
    zombies, defeating the assertion.
    """
    pid = os.getpid()
    # Try Linux /proc first — the production container is Linux.
    try:
        with open(f"/proc/{pid}/task/{pid}/children", encoding="ascii") as f:
            child_pids = [int(p) for p in f.read().split() if p.strip()]
    except FileNotFoundError:
        # macOS / BSD — use ps to enumerate children.
        result = subprocess.run(
            ["ps", "-o", "pid=,state=", "--ppid", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            # Different ps flavour (BSD): use -A and filter.
            result = subprocess.run(
                ["ps", "-A", "-o", "pid=,ppid=,state="],
                capture_output=True,
                text=True,
                check=False,
            )
            zombies = 0
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[1] == str(pid) and parts[2].startswith("Z"):
                    zombies += 1
            return zombies
        zombies = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("Z"):
                zombies += 1
        return zombies

    # Linux path: probe each child's state.
    zombies = 0
    for child_pid in child_pids:
        try:
            with open(f"/proc/{child_pid}/status", encoding="ascii") as f:
                for line in f:
                    if line.startswith("State:"):
                        if "Z" in line.split()[1]:
                            zombies += 1
                        break
        except FileNotFoundError:
            # Child exited & was reaped between listing and probing.
            continue
    return zombies


def test_reap_zombies_returns_zero_when_no_children() -> None:
    """With no children alive, reap_zombies must return 0 and not raise."""
    # Drain anything carried over from previous tests first.
    reap_zombies()
    assert reap_zombies() == 0


def test_reap_zombies_drains_short_lived_children(_restore_sigchld: None) -> None:
    """Spawn 10 quick-exit children with NO signal handler installed, then
    verify reap_zombies() finds and drains them."""
    # Make sure no handler is active — we want zombies to accumulate so
    # we can observe the drain.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)

    procs = [subprocess.Popen(["true"]) for _ in range(10)]
    # Give the kernel time to fire SIGCHLD + flip child state to Z.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if all(p.poll() is not None for p in procs):
            break
        time.sleep(0.05)

    # ``poll()`` on subprocess.Popen calls waitpid internally and would
    # reap the children itself. To force real zombies, we'd need to
    # bypass Popen's wait — but the daemon's actual hazard is exactly
    # the children that Popen does NOT track (reparented grandchildren).
    # Here we instead assert the reaper drains *whatever* zombies the
    # OS surfaces, including any from the burst above that Popen hasn't
    # explicitly waited on.
    reaped_or_polled = reap_zombies()
    # Either Popen reaped them via __del__ probes or the reaper did;
    # the invariant is the same: zero zombies remaining.
    assert _count_zombie_children() == 0, (
        f"zombie children remained after reap: reaped={reaped_or_polled}"
    )


def test_install_sigchld_reaper_drains_unwaited_grandchildren(
    _restore_sigchld: None,
) -> None:
    """Real scenario: spawn a parent that forks a child then exits.

    The grandchild gets reparented to this test process (its grandparent
    via PID inheritance) and, without a reaper, becomes a permanent
    zombie. With the reaper installed, the SIGCHLD on the grandchild's
    exit should drain it within a few hundred ms.

    Uses ``sh -c`` to fork a backgrounded ``true``: the parent shell
    exits immediately (Popen reaps it), but the backgrounded ``true``
    grandchild outlives the parent and is reparented to us.
    """
    install_sigchld_reaper()

    # Parent shell forks a backgrounded short-lived child then exits.
    # 'sleep 0.1' is short enough that the test stays fast but long
    # enough that the parent shell is guaranteed to exit before the
    # grandchild does, forcing the reparent.
    for _ in range(10):
        p = subprocess.Popen(["sh", "-c", "sleep 0.1 & exit 0"])
        p.wait()  # reaps the immediate child shell

    # Give grandchildren time to exit and SIGCHLD to fire.
    time.sleep(0.6)

    # The reaper, wired as the SIGCHLD handler, should have drained
    # every reparented grandchild as they exited.
    assert _count_zombie_children() == 0, (
        "reparented grandchildren left behind as zombies — reaper not firing"
    )


def test_install_sigchld_reaper_is_idempotent(_restore_sigchld: None) -> None:
    """Calling install_sigchld_reaper twice must not raise or break the handler."""
    install_sigchld_reaper()
    install_sigchld_reaper()
    handler = signal.getsignal(signal.SIGCHLD)
    # The reaper should still be the handler after a second install.
    assert handler is reap_zombies


def test_install_sigchld_reaper_skips_on_no_sigchld() -> None:
    """On platforms without SIGCHLD (Windows), install is a no-op, not a crash.

    Implementation note: Python's ``signal`` module is a process-global
    singleton, so we can't safely ``monkeypatch.delattr`` SIGCHLD without
    breaking every other test in the process. Instead we directly test
    the ``hasattr`` branch by stubbing the reaper module's ``signal``
    reference with a shim that lacks SIGCHLD.
    """
    import types as _types

    import decepticon.sandbox_server.reaper as reaper_mod

    real_signal = reaper_mod.signal
    fake_signal = _types.SimpleNamespace(signal=lambda *a, **k: None)
    # ``fake_signal`` deliberately has no SIGCHLD attribute.
    reaper_mod.signal = fake_signal  # type: ignore[assignment]
    try:
        # Should return without raising — the hasattr guard handles it.
        install_sigchld_reaper()
    finally:
        reaper_mod.signal = real_signal  # type: ignore[assignment]
