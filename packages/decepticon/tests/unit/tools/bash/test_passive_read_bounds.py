"""LRU + TTL bounds on the passive-read stale-poll tracker.

The tracker dict was previously unbounded: one entry per (workspace, session)
key, never pruned. In a long-lived server this grew without limit. These tests
lock in the bounded behavior:

* size cap: inserting more than ``_PASSIVE_MAX_ENTRIES`` keys evicts the
  least-recently-used entry;
* TTL: an entry untouched for longer than ``_PASSIVE_TTL_SECONDS`` is treated
  as absent and gets pruned on the next access.
"""

import importlib

from decepticon.tools.bash.bash import (
    _PASSIVE_MAX_ENTRIES,
    _PASSIVE_TTL_SECONDS,
    _passive_read_state,
    _track_passive_read,
)

# `from decepticon.tools.bash import bash` resolves to the @tool-decorated
# StructuredTool because the submodule shadows the package attribute. Reach the
# real module object explicitly so monkeypatch.setattr can target `_passive_clock`.
bash_mod = importlib.import_module("decepticon.tools.bash.bash")


def setup_function():
    _passive_read_state.clear()


def test_lru_evicts_oldest_when_over_capacity(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(bash_mod, "_passive_clock", lambda: clock["t"])

    # Fill exactly to capacity.
    for i in range(_PASSIVE_MAX_ENTRIES):
        clock["t"] += 1.0
        _track_passive_read("/w", f"s{i}", "x")
    assert len(_passive_read_state) == _PASSIVE_MAX_ENTRIES
    assert ("/w", "s0") in _passive_read_state

    # One more key — oldest ("s0") must be evicted.
    clock["t"] += 1.0
    _track_passive_read("/w", "overflow", "x")
    assert len(_passive_read_state) == _PASSIVE_MAX_ENTRIES
    assert ("/w", "s0") not in _passive_read_state
    assert ("/w", "overflow") in _passive_read_state


def test_recent_access_protects_from_eviction(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(bash_mod, "_passive_clock", lambda: clock["t"])

    for i in range(_PASSIVE_MAX_ENTRIES):
        clock["t"] += 1.0
        _track_passive_read("/w", f"s{i}", "x")

    # Touch s0 so it becomes most-recently-used.
    clock["t"] += 1.0
    _track_passive_read("/w", "s0", "x")

    # Add a new key — s0 must survive, the next-oldest (s1) is evicted.
    clock["t"] += 1.0
    _track_passive_read("/w", "overflow", "x")
    assert ("/w", "s0") in _passive_read_state
    assert ("/w", "s1") not in _passive_read_state


def test_ttl_expired_entry_pruned_on_access(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(bash_mod, "_passive_clock", lambda: clock["t"])

    # Seed an entry, then jump past the TTL.
    _track_passive_read("/w", "main", "same")
    _track_passive_read("/w", "main", "same")
    assert len(_passive_read_state[("/w", "main")][1]) == 2

    clock["t"] += _PASSIVE_TTL_SECONDS + 1.0
    # After TTL the prior history is gone — the next identical read starts
    # fresh, so it cannot trip the stale threshold on its own.
    result = _track_passive_read("/w", "main", "same")
    assert result is None
    assert len(_passive_read_state[("/w", "main")][1]) == 1


def test_ttl_prunes_idle_sibling_entries(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(bash_mod, "_passive_clock", lambda: clock["t"])

    _track_passive_read("/w", "idle", "x")
    clock["t"] += _PASSIVE_TTL_SECONDS + 1.0
    _track_passive_read("/w", "active", "x")
    # Idle sibling must be swept on the active access.
    assert ("/w", "idle") not in _passive_read_state
    assert ("/w", "active") in _passive_read_state
