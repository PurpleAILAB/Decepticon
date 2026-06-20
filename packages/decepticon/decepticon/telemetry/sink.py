"""TelemetrySink — the one object the agent stack talks to.

Wires consent (:mod:`config`) + sanitization (:mod:`sanitizer`) + delivery
(:mod:`exporter`) into a single ``record(event_type, payload, agent)`` call.
When telemetry is disabled (the default), the sink is a cheap no-op so it can be
unconditionally wired into the event path with zero overhead or behavior change.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from decepticon.telemetry.config import TelemetryConfig, TelemetryMode, resolve_config
from decepticon.telemetry.exporter import BatchExporter, Transport
from decepticon.telemetry.sanitizer import SCHEMA_VERSION, event_to_tier_a, scan_tier_c

log = logging.getLogger("decepticon.telemetry.sink")


class TelemetrySink:
    """Consent-gated, fail-closed Tier-A event sink."""

    def __init__(self, config: TelemetryConfig, *, transport: Transport | None = None) -> None:
        self._config = config
        self._extended = config.mode is TelemetryMode.EXTENDED
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

    def _envelope(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        tier = "B" if self._extended else "A"
        return {
            "schema_version": SCHEMA_VERSION,
            "tier": tier,
            "install_id": self._config.install_id,
            "client": {"decepticon_version": self._config.version, "os": self._config.os_name},
            "events": events,
        }

    def record(self, event_type: str, payload: dict[str, Any], agent: str | None = None) -> None:
        """Sanitize and enqueue one event. No-op when disabled; never raises."""
        if self._exporter is None:
            return
        try:
            ev = event_to_tier_a(
                {"type": event_type, "ts": _now(), "agent": agent, "payload": payload},
                self._extended,
            )
            if ev is None:
                return
            # Fail-closed: if anything in the mapped event still looks like Tier-C
            # content, drop it rather than ship it.
            if scan_tier_c(ev) is not None:
                log.debug("telemetry: dropped %s event failing local Tier-C scan", event_type)
                return
            self._exporter.record(ev)
        except Exception:  # noqa: BLE001 — telemetry must never break the agent
            log.debug("telemetry: record failed for %s", event_type, exc_info=True)

    def preview(self, sample_events: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the exact envelope that *would* be sent for ``sample_events``.

        Powers ``decepticon telemetry preview`` — transparency before any send.
        """
        mapped = [
            ev
            for rec in sample_events
            if (ev := event_to_tier_a(rec, self._extended)) is not None and scan_tier_c(ev) is None
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
