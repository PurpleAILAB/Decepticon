"""Compat shim — content moved to ``decepticon_core.utils.config``.

See ``decepticon.core.schemas`` for the rationale and the PEP 562
per-import DeprecationWarning pattern.
"""

from __future__ import annotations

import warnings
from typing import Any

import decepticon_core.utils.config as _target

_LEGACY = "decepticon.core.config"
_CANONICAL = "decepticon_core.utils.config"
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
