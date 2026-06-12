"""Adaptive poll-interval backoff in the tmux execute loops.

Every poll is a full ``tmux capture-pane -S -`` subprocess. The loops
back off geometrically while the screen is unchanged (×``POLL_BACKOFF_FACTOR``
up to ``POLL_INTERVAL × POLL_BACKOFF_MAX_MULTIPLIER``) and snap back to
``POLL_INTERVAL`` the moment new output appears, so quiet long-running
commands stop paying 2 captures/s while active output keeps the original
cadence. The cap is a multiplier so tests that patch ``POLL_INTERVAL``
down to milliseconds keep a proportionally fast cadence.
"""

from __future__ import annotations

import asyncio

import pytest

from decepticon.sandbox_kernel import tmux as tmux_mod
from decepticon.sandbox_kernel.tmux import TmuxSessionManager, _next_poll_interval

_BASE = 0.01
_MARKER_SCREEN = "output line\n[DCPTN:0:/workspace]"


# ---------------------------------------------------------------- _next_poll_interval


def test_next_poll_interval_grows_geometrically(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tmux_mod, "POLL_INTERVAL", 0.5)
    assert _next_poll_interval(0.5) == pytest.approx(0.75)
    assert _next_poll_interval(0.75) == pytest.approx(1.125)


def test_next_poll_interval_caps_at_multiplier_of_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tmux_mod, "POLL_INTERVAL", 0.5)
    cap = 0.5 * tmux_mod.POLL_BACKOFF_MAX_MULTIPLIER
    assert _next_poll_interval(1.9) == pytest.approx(cap)
    assert _next_poll_interval(cap) == pytest.approx(cap)


def test_next_poll_interval_cap_scales_with_patched_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Tests patch POLL_INTERVAL to milliseconds; the cap must follow,
    # not stay anchored at the production absolute.
    monkeypatch.setattr(tmux_mod, "POLL_INTERVAL", _BASE)
    cap = _BASE * tmux_mod.POLL_BACKOFF_MAX_MULTIPLIER
    interval = _BASE
    for _ in range(20):
        interval = _next_poll_interval(interval)
    assert interval == pytest.approx(cap)


# ---------------------------------------------------------------- loop behavior


def _scripted_manager(
    monkeypatch: pytest.MonkeyPatch, screens: list[str]
) -> tuple[TmuxSessionManager, list[float]]:
    """Manager whose _capture replays *screens* and whose sleeps are recorded.

    The first entry is the pre-send baseline capture; the rest are poll
    captures. Sleeps do not actually block, so the loop runs at full speed.
    """
    mgr = TmuxSessionManager(session="t", container_name="c")
    monkeypatch.setattr(mgr, "initialize", lambda: None)
    monkeypatch.setattr(mgr, "_send", lambda *a, **k: None)
    monkeypatch.setattr(mgr, "_forget_cached_state", lambda: None)
    monkeypatch.setattr(mgr, "_clear_screen", lambda: None)

    state = {"n": 0}

    def capture() -> str:
        screen = screens[min(state["n"], len(screens) - 1)]
        state["n"] += 1
        return screen

    monkeypatch.setattr(mgr, "_capture", capture)
    monkeypatch.setattr(tmux_mod, "POLL_INTERVAL", _BASE)

    sleeps: list[float] = []
    monkeypatch.setattr(tmux_mod.time, "sleep", sleeps.append)
    return mgr, sleeps


def test_sync_loop_backs_off_while_quiet_then_resets_on_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screens = [
        "base",  # baseline
        "base",  # quiet poll 1 → next interval grows
        "base",  # quiet poll 2
        "base",  # quiet poll 3
        "base\nprogress",  # output → interval snaps back to base
        "base\nprogress",  # quiet again → grows from base
        _MARKER_SCREEN,  # PS1 marker → completion
    ]
    mgr, sleeps = _scripted_manager(monkeypatch, screens)

    result = mgr.execute("./long-task.sh", is_input=False, timeout=30)

    assert "[ERROR]" not in result
    assert "[TIMEOUT]" not in result
    f = tmux_mod.POLL_BACKOFF_FACTOR
    assert sleeps == pytest.approx(
        [
            _BASE,  # first poll always at base cadence
            _BASE * f,  # after quiet poll 1
            _BASE * f * f,  # after quiet poll 2
            _BASE * f * f * f,  # after quiet poll 3
            _BASE,  # output appeared → reset
            _BASE * f,  # quiet again → grows from base
        ]
    )


def test_sync_loop_backoff_never_exceeds_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    quiet_polls = 24
    screens = ["base"] * (1 + quiet_polls) + [_MARKER_SCREEN]
    mgr, sleeps = _scripted_manager(monkeypatch, screens)

    result = mgr.execute("sleep 600", is_input=False, timeout=30)

    assert "[ERROR]" not in result
    cap = _BASE * tmux_mod.POLL_BACKOFF_MAX_MULTIPLIER
    assert max(sleeps) <= cap + 1e-9
    # the tail of a long quiet stretch sits at the cap, not at base cadence
    assert sleeps[-1] == pytest.approx(cap)


def test_async_loop_backs_off_while_quiet_then_resets_on_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screens = [
        "base",
        "base",
        "base",
        "base\nprogress",
        "base\nprogress",
        _MARKER_SCREEN,
    ]
    mgr, _ = _scripted_manager(monkeypatch, screens)

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(tmux_mod.asyncio, "sleep", fake_sleep)

    result = asyncio.run(mgr.execute_async("./long-task.sh", is_input=False, timeout=30))

    assert "[ERROR]" not in result
    assert "[TIMEOUT]" not in result
    f = tmux_mod.POLL_BACKOFF_FACTOR
    assert sleeps == pytest.approx(
        [
            _BASE,
            _BASE * f,
            _BASE * f * f,
            _BASE,  # output appeared → reset
            _BASE * f,
        ]
    )
