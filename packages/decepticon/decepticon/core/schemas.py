"""Compat shim — content moved to ``decepticon_core.types.engagement``.

Phase 1 of the core/framework/sdk split relocated pure-pydantic types
into the contract layer. This shim keeps the legacy import path
working until the 2.0.0 cleanup; the PEP 562 ``__getattr__`` hook
emits one ``DeprecationWarning`` per attribute on first access so
the migration list surfaces in test logs (spec §7.3).
"""

from __future__ import annotations

import warnings
from typing import Any

import decepticon_core.types.engagement as _target

_LEGACY = "decepticon.core.schemas"
_CANONICAL = "decepticon_core.types.engagement"
_seen: set[str] = set()


def __getattr__(name: str) -> Any:
    if name.startswith("_"):
        # Dunder/private lookups (e.g. Pythons own __path__ probe during
        # `from X import Y`) shouldn't emit deprecation noise.
        raise AttributeError(name)
    if name not in _seen:
        _seen.add(name)
        warnings.warn(
            f"{_LEGACY}.{name} is deprecated; import from {_CANONICAL}.{name} instead "
            f"(legacy path removed at 2.0.0)",
            DeprecationWarning,
            stacklevel=2,
        )
    return getattr(_target, name)


def __dir__() -> list[str]:
    return dir(_target)
