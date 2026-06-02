"""Cross-platform unit tests for the bounded lock-retry helper.

The Windows ``_acquire_lock`` branch previously spun forever on
``msvcrt.locking`` ``OSError``. The retry policy is now extracted into
``_retry_lock`` so it can be tested on Linux CI without ``msvcrt``.
"""

from __future__ import annotations

import pytest

from decepticon.runtime.event_log import LOCK_ACQUIRE_TIMEOUT_S, _retry_lock


class _FailNTimes:
    """Acquire callable that raises ``OSError`` the first ``n`` calls."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1
        if self.calls <= self.n:
            raise OSError("locked")


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, dt: float) -> None:
        self.sleeps.append(dt)
        self.now += dt


def test_retry_lock_returns_when_acquire_eventually_succeeds() -> None:
    clock = _FakeClock()
    acquire = _FailNTimes(2)
    _retry_lock(acquire, timeout=10.0, sleep=clock.sleep, clock=clock.time)
    assert acquire.calls == 3
    assert len(clock.sleeps) == 2
    assert all(0 < s <= 1.0 for s in clock.sleeps)


def test_retry_lock_raises_timeout_when_deadline_exceeded() -> None:
    clock = _FakeClock()

    def always_fail() -> None:
        raise OSError("locked")

    with pytest.raises(TimeoutError):
        _retry_lock(always_fail, timeout=0.5, sleep=clock.sleep, clock=clock.time)

    assert len(clock.sleeps) >= 1
    assert clock.now >= 0.5


def test_retry_lock_bounded_sleeps_with_backoff() -> None:
    clock = _FakeClock()

    def always_fail() -> None:
        raise OSError("locked")

    with pytest.raises(TimeoutError):
        _retry_lock(always_fail, timeout=2.0, sleep=clock.sleep, clock=clock.time)

    assert len(clock.sleeps) < 1000
    assert clock.sleeps == sorted(clock.sleeps)
    assert max(clock.sleeps) <= 1.0


def test_retry_lock_succeeds_on_first_try_without_sleeping() -> None:
    clock = _FakeClock()
    acquire = _FailNTimes(0)
    _retry_lock(acquire, timeout=1.0, sleep=clock.sleep, clock=clock.time)
    assert acquire.calls == 1
    assert clock.sleeps == []


def test_lock_acquire_timeout_default_is_sane() -> None:
    assert 1.0 <= LOCK_ACQUIRE_TIMEOUT_S <= 120.0
