"""Telemetry consent + configuration resolution.

Opt-in by design (decision §0.4): telemetry is OFF unless the user explicitly
enables it, and ``DO_NOT_TRACK`` always forces it off. Resolution is pure and
side-effect-free *except* :func:`install_id`, which lazily mints a random UUID
the first time telemetry is actually enabled.

Environment surface (documented in ``TELEMETRY.md``):

* ``DECEPTICON_TELEMETRY``          ``off`` | ``basic`` | ``extended``  (default ``off``)
* ``DO_NOT_TRACK``                  truthy → forces ``off`` (standard)
* ``DECEPTICON_TELEMETRY_ENDPOINT`` gateway URL; unset → effectively ``off``
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}


class TelemetryMode(str, Enum):
    """How much the user consented to share."""

    OFF = "off"
    BASIC = "basic"  # Tier A only — structural, non-identifying
    EXTENDED = "extended"  # Tier A + B — adds sanitized semantic classification


def _truthy(raw: str | None) -> bool:
    return raw is not None and raw.strip().lower() in _TRUTHY


def resolve_mode(env: dict[str, str] | None = None) -> TelemetryMode:
    """Resolve the effective consent mode. Fail-closed: unknown → OFF."""
    e = env if env is not None else dict(os.environ)
    if _truthy(e.get("DO_NOT_TRACK")):
        return TelemetryMode.OFF
    raw = (e.get("DECEPTICON_TELEMETRY") or "off").strip().lower()
    try:
        return TelemetryMode(raw)
    except ValueError:
        return TelemetryMode.OFF  # unrecognized value → off, never guess up


def _home(env: dict[str, str]) -> Path:
    raw = env.get("DECEPTICON_HOME") or "~/.decepticon"
    return Path(raw).expanduser()


def _opt_out_marker(env: dict[str, str]) -> Path:
    return _home(env) / "telemetry" / "opt_out"


def is_opted_out(env: dict[str, str] | None = None) -> bool:
    """True when a persistent opt-out marker exists (``telemetry off``)."""
    e = env if env is not None else dict(os.environ)
    try:
        return _opt_out_marker(e).exists()
    except OSError:
        return False


def set_opted_out(opted_out: bool, env: dict[str, str] | None = None) -> None:
    """Create/remove the persistent opt-out marker."""
    e = env if env is not None else dict(os.environ)
    marker = _opt_out_marker(e)
    if opted_out:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("opted out\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()


def install_id(env: dict[str, str] | None = None) -> str:
    """Return the persistent anonymous install id, minting one on first use.

    A random UUID (never machine/IP derived) stored under
    ``$DECEPTICON_HOME/telemetry/install_id``. If the path is unwritable we fall
    back to an ephemeral id so telemetry degrades rather than crashes.
    """
    e = env if env is not None else dict(os.environ)
    path = _home(e) / "telemetry" / "install_id"
    try:
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        new_id = str(uuid.uuid4())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_id, encoding="utf-8")
        return new_id
    except OSError:
        return str(uuid.uuid4())


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    """Fully resolved telemetry settings for a process."""

    mode: TelemetryMode
    endpoint: str | None
    install_id: str
    version: str
    os_name: str

    @property
    def enabled(self) -> bool:
        """Telemetry actually ships only with consent AND a destination."""
        return self.mode is not TelemetryMode.OFF and bool(self.endpoint)


def resolve_config(env: dict[str, str] | None = None) -> TelemetryConfig:
    """Resolve consent, endpoint, and identity into one config object."""
    import platform

    e = env if env is not None else dict(os.environ)
    # A persistent opt-out (``telemetry off``) overrides any env mode.
    mode = TelemetryMode.OFF if is_opted_out(e) else resolve_mode(e)
    endpoint = (e.get("DECEPTICON_TELEMETRY_ENDPOINT") or "").strip() or None
    # Only mint/read an install id when telemetry is actually on — keeps OFF
    # purely side-effect-free.
    iid = (
        install_id(e)
        if (mode is not TelemetryMode.OFF and endpoint)
        else "00000000-0000-0000-0000-000000000000"
    )
    sys_map = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}
    return TelemetryConfig(
        mode=mode,
        endpoint=endpoint,
        install_id=iid,
        version=e.get("DECEPTICON_VERSION") or _detect_version(),
        os_name=sys_map.get(platform.system(), "linux"),
    )


def _detect_version() -> str:
    try:
        from importlib.metadata import version

        return version("decepticon")
    except Exception:  # noqa: BLE001 — version is best-effort, never fatal
        return "0.0.0"
