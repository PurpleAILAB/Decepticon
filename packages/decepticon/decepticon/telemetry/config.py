"""Telemetry consent + configuration resolution.

The PRODUCT default is opt-out: the launcher's onboard wizard asks for consent
(default yes) and the shipped ``.env`` template defaults ``DECEPTICON_TELEMETRY``
to ``research``, so consenting users collect by default while ``DO_NOT_TRACK`` and
``decepticon-cli telemetry off`` always force it off. This module is the
fail-SAFE floor: when ``DECEPTICON_TELEMETRY`` is unset (e.g. standalone library
use, never onboarded), it resolves to ``off`` — the value, not the absence,
turns telemetry on. Resolution is pure and side-effect-free *except*
:func:`install_id`, which lazily mints a random UUID the first time telemetry is
actually enabled.

Environment surface (documented in ``TELEMETRY.md``):

* ``DECEPTICON_TELEMETRY``          ``off`` | ``basic`` | ``research`` (template default ``research``; unset → ``off``)
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
    """How much the user consented to share.

    ``research`` adds identifier-masked reasoning/trajectory capture on top of
    the anonymous structural ``basic`` tier (see ``telemetry.trajectory``).
    """

    OFF = "off"
    BASIC = "basic"  # anonymous structural artifacts only
    RESEARCH = "research"  # basic + identifier-masked reasoning/trajectory corpus


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


def _mode_file(env: dict[str, str]) -> Path:
    return _home(env) / "telemetry" / "mode"


def persisted_mode(env: dict[str, str] | None = None) -> TelemetryMode | None:
    """Read the persisted opt-in mode (``telemetry enable …``), if any."""
    e = env if env is not None else dict(os.environ)
    try:
        raw = _mode_file(e).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    try:
        return TelemetryMode(raw)
    except ValueError:
        return None


def set_persisted_mode(mode: TelemetryMode, env: dict[str, str] | None = None) -> None:
    """Persist an explicit consent choice from ``telemetry enable``/``off``.

    ``OFF`` writes the opt-out marker (and clears any mode); ``basic``/
    ``extended`` write the mode and clear the opt-out marker.
    """
    e = env if env is not None else dict(os.environ)
    mfile = _mode_file(e)
    if mode is TelemetryMode.OFF:
        set_opted_out(True, e)
        if mfile.exists():
            mfile.unlink()
        return
    set_opted_out(False, e)
    mfile.parent.mkdir(parents=True, exist_ok=True)
    mfile.write_text(mode.value, encoding="utf-8")


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
    # Precedence: DO_NOT_TRACK / opt-out force off; then an env override; then
    # the persisted opt-in choice; else off.
    if _truthy(e.get("DO_NOT_TRACK")) or is_opted_out(e):
        mode = TelemetryMode.OFF
    elif (e.get("DECEPTICON_TELEMETRY") or "").strip():
        mode = resolve_mode(e)
    else:
        mode = persisted_mode(e) or TelemetryMode.OFF
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
