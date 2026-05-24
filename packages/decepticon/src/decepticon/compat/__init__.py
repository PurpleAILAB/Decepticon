"""Backward-compatibility shim layer for the core/framework/sdk split.

Per spec §7.3 of
``docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md``,
this module ships the one-release migration shim:

  * Legacy import paths (``decepticon.core.schemas``,
    ``decepticon.llm.models``, ``decepticon.tools.research.graph``,
    ``decepticon.plugin_loader``, ``decepticon.core.config``,
    ``decepticon.core.logging``) keep working via the per-file
    re-export modules in Phase 1.
  * ``register_legacy_imports()`` (default-on, opt-out via
    ``DECEPTICON_NO_COMPAT=1``) raises ``DeprecationWarning`` once on
    first call to surface the migration list in test logs.

The shim is REMOVED at ``2.0.0``. Phase 2 of the redesign rewrites
all internal framework call sites to import from
``decepticon_core.*`` directly; downstream consumers we don't know
about are the audience for this shim layer.
"""

from __future__ import annotations

import os
import warnings

_REGISTERED: bool = False

_LEGACY_PATH_NOTES: tuple[tuple[str, str], ...] = (
    ("decepticon.core.schemas", "decepticon_core.types.engagement"),
    ("decepticon.llm.models", "decepticon_core.types.llm"),
    ("decepticon.tools.research.graph", "decepticon_core.types.kg"),
    ("decepticon.plugin_loader", "decepticon_core.plugin_loader"),
    ("decepticon.core.config", "decepticon_core.utils.config"),
    ("decepticon.core.logging", "decepticon_core.utils.logging"),
    (
        "decepticon.agents.middleware_slots",
        "decepticon_core.contracts.slots (enum/SLOTS_PER_ROLE only)",
    ),
)


def register_legacy_imports() -> None:
    """Enable the Phase 1 compat shim layer.

    Default-on via ``decepticon.__init__`` (Phase 2 wires this);
    opt-out via ``DECEPTICON_NO_COMPAT=1`` in the environment. Idempotent —
    repeated calls are no-ops.

    Emits a single ``DeprecationWarning`` per process listing the
    legacy → canonical path mapping so test logs surface the migration
    list. The legacy paths keep working until ``2.0.0`` — the warning
    is informational, not blocking.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    if os.environ.get("DECEPTICON_NO_COMPAT", "").strip().lower() in {"1", "true", "yes"}:
        _REGISTERED = True
        return

    lines = ["Decepticon Phase 1 compat shims active. Migrate the following paths before 2.0.0:"]
    for legacy, canonical in _LEGACY_PATH_NOTES:
        lines.append(f"  - {legacy}  ->  {canonical}")
    warnings.warn(
        "\n".join(lines),
        DeprecationWarning,
        stacklevel=2,
    )
    _REGISTERED = True


__all__ = ["register_legacy_imports"]
