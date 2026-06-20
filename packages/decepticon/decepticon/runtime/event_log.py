"""Append-only engagement event log with cross-platform file locking.

The orchestrator (and the future ``resume <engagement_id>`` command) needs
a durable, line-oriented record of what happened during a run that
survives crash or Ctrl-C. This module defines that contract:

* one ``events.jsonl`` file per engagement under
  ``engagements/<id>/events.jsonl``,
* append-only writes with platform-appropriate exclusive file locking
  (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows) so concurrent
  writers cannot interleave a single event's JSON line,
* a small enum of event types so consumers can dispatch without
  string-matching free-form payloads,
* a ``read_events()`` helper that yields events in order and gracefully
  skips malformed lines (so a torn final line does not break replay).

The CLI ``--resume <id>`` wiring (Go launcher + TS REPL + Python
middleware) is intentionally out of scope for this PR; the Python event
log lands first as a clean dependency-free unit that the CLI layer can
adopt next.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger("decepticon.runtime.event_log")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v > 0 else default


LOCK_ACQUIRE_TIMEOUT_S: float = _env_float("DECEPTICON_EVENT_LOG_LOCK_TIMEOUT_S", 10.0)
_LOCK_RETRY_INITIAL_SLEEP_S: float = 0.01
_LOCK_RETRY_MAX_SLEEP_S: float = 1.0


def _retry_lock(
    acquire: Callable[[], None],
    *,
    timeout: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> None:
    """Call ``acquire`` until it returns, with capped exponential backoff.

    ``acquire`` must raise ``OSError`` on contention and return on
    success. The retry stops once the elapsed time since the first
    attempt exceeds ``timeout``; in that case the last ``OSError`` is
    re-raised as :class:`TimeoutError` so callers fail fast instead of
    spinning forever on a stale lock.
    """
    deadline = clock() + timeout
    delay = _LOCK_RETRY_INITIAL_SLEEP_S
    last_err: OSError | None = None
    while True:
        try:
            acquire()
            return
        except OSError as e:
            last_err = e
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError(f"event-log lock not acquired within {timeout:.3f}s") from last_err
        sleep(min(delay, remaining))
        delay = min(delay * 2, _LOCK_RETRY_MAX_SLEEP_S)


class EventType(str, Enum):
    """All engagement event types the orchestrator may emit."""

    ENGAGEMENT_START = "engagement.start"
    ENGAGEMENT_END = "engagement.end"
    ENGAGEMENT_CHECKPOINT = "engagement.checkpoint"
    AGENT_TURN = "agent.turn"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    LLM_CALL = "llm.call"
    LLM_RESPONSE = "llm.response"
    FINDING_CREATED = "finding.created"
    OPPLAN_UPDATE = "opplan.update"


@dataclass(frozen=True, slots=True)
class EngagementEvent:
    """One line in an engagement's ``events.jsonl``.

    Fields:

    * ``ts`` — wall-clock timestamp (seconds since epoch).
    * ``type`` — one of :class:`EventType` (kept as ``str`` on disk so the
      file remains parseable even if a new type is added in a later
      version).
    * ``agent`` — emitting agent name, when known.
    * ``payload`` — type-specific data (kept untyped to keep the schema
      forward-compatible).
    """

    ts: float
    type: str
    agent: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        obj: dict[str, Any] = {
            "ts": self.ts,
            "type": self.type,
            "payload": self.payload,
        }
        if self.agent is not None:
            obj["agent"] = self.agent
        return json.dumps(obj, default=str, ensure_ascii=False)

    @classmethod
    def from_json_line(cls, line: str) -> EngagementEvent | None:
        line = line.strip()
        if not line:
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        try:
            return cls(
                ts=float(obj.get("ts", 0.0)),
                type=str(obj.get("type", "")),
                agent=obj.get("agent"),
                payload=obj.get("payload") or {},
            )
        except (TypeError, ValueError):
            return None


def _engagement_events_path(workspace_root: Path, engagement_id: str) -> Path:
    return workspace_root / "engagements" / engagement_id / "events.jsonl"


def _acquire_lock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        _retry_lock(
            lambda: msvcrt.locking(fd, msvcrt.LK_LOCK, 1),
            timeout=LOCK_ACQUIRE_TIMEOUT_S,
            sleep=time.sleep,
            clock=time.monotonic,
        )
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _release_lock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            log.warning("event-log lock release failed", exc_info=True)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class EventLog:
    """Append-only events.jsonl writer for one engagement.

    Instances are cheap; create one per engagement and reuse it for the
    lifetime of the run. ``append()`` is safe under concurrent threads
    (via the in-process ``_lock``) and concurrent processes (via the
    platform file lock). A torn write attempt (process killed
    mid-write) cannot corrupt earlier events — the lock blocks any
    second writer until the current line is fully flushed and the lock
    released.
    """

    def __init__(self, workspace_root: str | os.PathLike[str], engagement_id: str) -> None:
        self._init_at(_engagement_events_path(Path(workspace_root), engagement_id), engagement_id)

    @classmethod
    def for_workspace(
        cls, workspace_dir: str | os.PathLike[str], engagement_id: str = ""
    ) -> EventLog:
        """Build a log writing directly to ``<workspace_dir>/events.jsonl``.

        Unlike :meth:`__init__`, this skips the ``engagements/<id>`` nesting:
        the engagement workspace root *is* the directory shutdown.py and the
        web dashboard read from. ``engagement_id`` is retained only to tag
        emitted events, never to shape the path.
        """
        self = cls.__new__(cls)
        self._init_at(Path(workspace_dir) / "events.jsonl", engagement_id)
        return self

    def _init_at(self, path: Path, engagement_id: str) -> None:
        self._engagement_id = engagement_id
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def engagement_id(self) -> str:
        return self._engagement_id

    def append(
        self,
        event_type: str | EventType,
        payload: dict[str, Any] | None = None,
        *,
        agent: str | None = None,
        ts: float | None = None,
    ) -> EngagementEvent:
        """Append one event line atomically. Returns the rendered event."""
        if isinstance(event_type, EventType):
            type_str = event_type.value
        else:
            type_str = str(event_type)
        event = EngagementEvent(
            ts=ts if ts is not None else time.time(),
            type=type_str,
            agent=agent,
            payload=payload or {},
        )
        line = event.to_json_line() + "\n"
        with self._lock:
            with open(self._path, "ab") as fh:
                fd = fh.fileno()
                _acquire_lock(fd)
                try:
                    fh.write(line.encode("utf-8"))
                    fh.flush()
                    os.fsync(fd)
                finally:
                    _release_lock(fd)
        return event

    def read(self) -> Iterator[EngagementEvent]:
        """Iterate events in the order they were appended.

        Malformed or torn lines are skipped silently so a process killed
        mid-write cannot make the entire log unreadable.
        """
        yield from read_events(self._path)


def read_events(path: str | os.PathLike[str]) -> Iterator[EngagementEvent]:
    """Yield :class:`EngagementEvent` objects from ``path`` in order."""
    p = Path(path)
    if not p.exists():
        return
    with open(p, "rb") as fh:
        for raw in fh:
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            event = EngagementEvent.from_json_line(line)
            if event is not None:
                yield event


__all__ = [
    "EngagementEvent",
    "EventLog",
    "EventType",
    "read_events",
]
