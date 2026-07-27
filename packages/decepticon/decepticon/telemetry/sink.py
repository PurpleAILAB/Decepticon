"""TelemetrySink — the one object the agent stack talks to.

Wires consent (:mod:`config`) + sanitization (:mod:`sanitizer`) + delivery
(:mod:`exporter`) into a single ``record(event_type, payload, agent)`` call.
When telemetry is disabled (the default), the sink is a cheap no-op so it can be
unconditionally wired into the event path with zero overhead or behavior change.
"""

from __future__ import annotations

import logging
import os
import threading
from contextvars import ContextVar, Token
from functools import lru_cache
from typing import Any

from decepticon.telemetry.config import TelemetryConfig, TelemetryMode, resolve_config
from decepticon.telemetry.exporter import BatchExporter, Transport
from decepticon.telemetry.redact import Redactor
from decepticon.telemetry.sanitizer import SCHEMA_VERSION, event_to_tier_a, scan_tier_c, slug

log = logging.getLogger("decepticon.telemetry.sink")


class TelemetrySink:
    """Consent-gated, fail-closed Tier-A event sink."""

    def __init__(self, config: TelemetryConfig, *, transport: Transport | None = None) -> None:
        self._config = config
        self._research = config.mode is TelemetryMode.RESEARCH
        # One masker per sink/session so identifiers map to STABLE placeholders
        # across a whole trajectory (reasoning stays coherent for training).
        self._redactor = Redactor()
        # Per-engagement trajectory step counters, shared by every agent in the
        # process (see :meth:`next_step`).
        self._steps: dict[str, int] = {}
        self._step_lock = threading.Lock()
        # Tier-C drops, counted by class. Fail-closed dropping is correct but was
        # invisible (a debug log line), so there was no way to tell a quiet run
        # from a run whose corpus was being silently discarded.
        self._drops: dict[str, int] = {}
        self._exporter: BatchExporter | None = None
        if config.enabled and config.endpoint:
            self._exporter = BatchExporter(
                endpoint=config.endpoint,
                envelope=self._envelope,
                transport=transport,
            )

    @property
    def enabled(self) -> bool:
        return self._exporter is not None

    @property
    def research(self) -> bool:
        """True when reasoning/trajectory capture is active (research consent)."""
        return self._exporter is not None and self._research

    def _envelope(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        # Drop tallies ride along with a batch we were sending anyway — no extra
        # request, and the counts stay adjacent to the events they were dropped from.
        events = events + self._drain_drops()
        client: dict[str, Any] = {
            "decepticon_version": self._config.version,
            "os": self._config.os_name,
        }
        # Optional non-identifying runtime dims; omitted when unset so the
        # gateway's strict schema never sees an empty/invalid value.
        if self._config.arch:
            client["arch"] = self._config.arch
        if self._config.py_version:
            client["py"] = self._config.py_version
        return {
            "schema_version": SCHEMA_VERSION,
            "tier": "R" if self._research else "A",
            "install_id": self._config.install_id,
            "client": client,
            "events": events,
        }

    def record(
        self,
        event_type: str,
        payload: dict[str, Any],
        agent: str | None = None,
        *,
        session_id: str | None = None,
    ) -> None:
        """Sanitize and enqueue one event. No-op when disabled; never raises.

        ``session_id`` is the per-engagement hash (from :func:`session_id_for`).
        Stamping it onto every event — not just trajectory steps — lets the
        analytics backend group an install's events *by engagement* (kill-chain
        depth, tools-per-engagement, reach) instead of conflating every
        engagement that ran on one machine under ``install_id``.
        """
        if self._exporter is None:
            return
        try:
            ev = event_to_tier_a(
                {"type": event_type, "ts": _now(), "agent": agent, "payload": payload}
            )
            if ev is None:
                return
            # Engagement grouping key — a hash, never the raw engagement name.
            # Falls back to the ambient session so tool-side emits (findings)
            # group with the engagement that produced them.
            sid = session_id or current_session()
            if sid:
                ev["session_id"] = sid
            # Fail-closed: if anything in the mapped event still looks like Tier-C
            # content, drop it rather than ship it.
            hit = scan_tier_c(ev)
            if hit is not None:
                self._count_drop(hit[0])
                log.debug("telemetry: dropped %s event failing local Tier-C scan", event_type)
                return
            self._exporter.record(ev)
        except Exception:  # noqa: BLE001 — telemetry must never break the agent
            log.debug("telemetry: record failed for %s", event_type, exc_info=True)

    def record_finding(
        self,
        *,
        severity: str | None = None,
        cwe: list[str] | None = None,
        mitre: list[str] | None = None,
        phase: str | None = None,
        confidence: str | None = None,
        detected: bool | None = None,
        agent: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record a validated finding's GROUND-TRUTH classification.

        These fields are produced by the engagement itself (the ``Finding`` model
        / KG), not inferred — `severity`, `cwe`, `mitre`, `phase`, `confidence`,
        and the purple-team `detected` flag. Identifiers (target, description,
        evidence) are never passed in. Tier A: this is structural, non-identifying
        signal about what the agent actually found.
        """
        payload: dict[str, Any] = {}
        if severity:
            payload["severity"] = severity
        if cwe:
            payload["cwe"] = cwe
        if mitre:
            payload["mitre_techniques"] = mitre
        if phase:
            payload["phase"] = phase
        if confidence:
            payload["confidence"] = confidence
        if detected is not None:
            payload["detected"] = "yes" if detected else "no"
        self.record("finding.created", payload, agent, session_id=session_id)

    def record_phase(
        self,
        phase: str,
        status: str,
        agent: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record an OPPLAN objective phase + status — where the engagement is.

        Ground truth from the OPPLAN tracker (``ObjectivePhase`` / status). Tier A.
        """
        self.record(
            "opplan.update", {"phase": phase, "status": status}, agent, session_id=session_id
        )

    def _count_drop(self, klass: str) -> None:
        """Tally one fail-closed drop by CLASS only — never the value or path."""
        with self._step_lock:
            self._drops[klass] = self._drops.get(klass, 0) + 1

    def _drain_drops(self) -> list[dict[str, Any]]:
        """Pop the drop tallies as events, to ride along with the next batch."""
        with self._step_lock:
            if not self._drops:
                return []
            drops, self._drops = self._drops, {}
        return [
            {"type": "telemetry.drop", "ts": _now(), "category": klass, "count": n}
            for klass, n in drops.items()
        ]

    def next_step(self, session_id: str) -> int:
        """Next monotonic step index for ``session_id``.

        Lives on the process-wide sink, not on the middleware: every agent in an
        engagement builds its OWN middleware instance, so a per-instance counter
        restarted at 0 for each specialist and `ORDER BY step` reconstructed a
        scrambled trajectory (measured: 71% duplicate indices in one session).
        """
        with self._step_lock:
            n = self._steps.get(session_id, 0)
            self._steps[session_id] = n + 1
            return n

    def add_known_targets(self, targets: list[str], ptype: str = "HOST") -> None:
        """Feed the session masker the engagement's known terms (RoE scope).

        Lets the redactor mask the *actual* targets with certainty — covering
        identifiers the generic detectors miss. ``ptype="ORG"`` is for the
        client / engagement slug, which no detector can find but the engagement
        already knows. No-op unless research is active.
        """
        if self._exporter is None or not self._research or not targets:
            return
        self._redactor.add_known(targets, ptype)

    def record_step(
        self, step: dict[str, Any], agent: str | None = None, *, model: str | None = None
    ) -> None:
        """Record an identifier-MASKED reasoning/trajectory step (RESEARCH only).

        ``step`` carries the raw turn as-is (role, session_id, step, and the text
        — human objective / agent reasoning / tool args+observation). Every string
        is masked by the session Redactor — target
        identifiers become stable placeholders, the reasoning structure is kept —
        then the masked step is fail-closed re-scanned; if any identifier slipped
        through, the WHOLE step is dropped rather than shipped. No-op unless
        research consent is active; never raises.
        """
        if self._exporter is None or not self._research:
            return
        try:
            masked = self._redactor.redact_obj(step)
            if not isinstance(masked, dict):
                return
            # Fail-closed: drop the step if any raw identifier survived masking.
            hit = scan_tier_c(masked)
            if hit is not None:
                self._count_drop(hit[0])
                log.debug("telemetry: dropped trajectory step failing post-mask Tier-C scan")
                return
            ev: dict[str, Any] = {"type": "trajectory.step", "ts": _now(), **masked}
            # Slugified like every other event's agent: an off-pattern value
            # (a plugin role with a space) fails the gateway's strict schema and
            # takes the whole batch down with it.
            if agent and (agent_slug := slug(agent)):
                ev["agent"] = agent_slug
            # Which model produced this turn — a corpus without it cannot tell
            # strong reasoning from weak. Slugified: raw ids carry "/"
            # ("anthropic/claude-haiku-4-5"), which the gateway's Slug rejects.
            if model and (model_slug := slug(model)):
                ev["model"] = model_slug
            self._exporter.record(ev)
        except Exception:  # noqa: BLE001 — telemetry must never break the agent
            log.debug("telemetry: record_step failed", exc_info=True)

    def preview(self, sample_events: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the exact envelope that *would* be sent for ``sample_events``.

        Powers ``decepticon telemetry preview`` — transparency before any send.
        """
        mapped = [
            ev
            for rec in sample_events
            if (ev := event_to_tier_a(rec)) is not None and scan_tier_c(ev) is None
        ]
        return self._envelope(mapped)

    def flush(self) -> None:
        if self._exporter is not None:
            self._exporter.flush()

    def close(self) -> None:
        if self._exporter is not None:
            self._exporter.close()


def _now() -> float:
    import time

    return time.time()


# The engagement whose tool call is currently executing. Set by
# ``EventLogMiddleware`` around each tool invocation and read by tool-side emits
# (findings) that have no other handle on the run: a tool receives no state and
# cannot read the run config reliably, so without this every finding shipped
# without a session and could not be grouped with the engagement that produced it.
_current_session: ContextVar[str | None] = ContextVar("decepticon_telemetry_session", default=None)


def set_current_session(session_id: str | None) -> Token[str | None]:
    """Bind the session id for the current context. Returns a reset token."""
    return _current_session.set(session_id)


def reset_current_session(token: Token[str | None]) -> None:
    _current_session.reset(token)


def current_session() -> str | None:
    """The session id bound to this context, if any."""
    return _current_session.get()


@lru_cache(maxsize=1)
def _session_salt() -> str:
    """The anonymous install id, used to scope session ids to this machine.

    Cached: resolving it touches the filesystem, and it cannot change within a
    process.
    """
    return resolve_config().install_id


def session_id_for(engagement: str | None) -> str:
    """Stable per-engagement session id (sha256[:16]).

    The engagement name may carry a client/org name, so it is **never** sent
    raw — this hash is the grouping key shared by every event of one engagement
    (trajectory steps, tool calls, findings, OPPLAN phases). Canonical home for
    the hash so the middleware and the OPPLAN/finding tools all agree.

    Salted with the install id, because the engagement name alone is NOT unique
    across users: measured in production, ``sha256("test")`` was shared by 37
    installs and ``sha256("default-engagement")`` by 27, merging unrelated
    people's work into one "engagement" — 28.3% of all events sat in a colliding
    session. Salting keeps the id stable for a given install (so a resumed
    engagement keeps its id) while making it unique across machines.
    """
    import hashlib

    return hashlib.sha256(f"{_session_salt()}\x00{engagement or ''}".encode()).hexdigest()[:16]


# ── process-wide lazy singleton (what middleware uses) ───────────────────────

_SINGLETON: TelemetrySink | None = None
_DISABLED = TelemetrySink(
    TelemetryConfig(
        mode=TelemetryMode.OFF, endpoint=None, install_id="", version="0.0.0", os_name="linux"
    )
)


def get_sink() -> TelemetrySink:
    """Return the process telemetry sink, building it from env on first use.

    Returns a shared disabled no-op sink when telemetry is off, so callers can
    wire it unconditionally. Set ``DECEPTICON_TELEMETRY_DISABLE_SINK`` to force
    the no-op (used by tests).
    """
    global _SINGLETON
    if os.environ.get("DECEPTICON_TELEMETRY_DISABLE_SINK"):
        return _DISABLED
    if _SINGLETON is None:
        config = resolve_config()
        _SINGLETON = TelemetrySink(config) if config.enabled else _DISABLED
    return _SINGLETON
