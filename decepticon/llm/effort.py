"""Reasoning-effort knob — Strix-style ``DECEPTICON_REASONING_EFFORT``.

Single env-driven setting that maps to a bundle of provider kwargs:

================  ======================================================
Effort            Behaviour
================  ======================================================
``quick``         low temperature, low max_tokens, ``reasoning_effort=low``
``standard``      defaults — no overrides applied
``deep``          high temperature ceiling, large max_tokens, ``reasoning_effort=high``
================  ======================================================

The factory layer already hardcodes per-provider thinking-mode defaults
(see :mod:`decepticon.llm.factory`'s ``_model_is_deepseek_thinking`` /
DeepSeek ``reasoning_effort='high'`` injection). This module provides a
*runtime override* the launcher / CLI flag wires through without touching
the factory: the agent constructor calls
:func:`apply_effort_to_chat_model` after the ChatOpenAI instance is built
but before it's passed into ``create_agent`` so the override flows into
every subsequent request.

Strix exposes the same knob via ``STRIX_REASONING_EFFORT`` — Decepticon
keeps the env name in sync with its own naming convention but accepts the
Strix variant as a fallback so users porting from Strix don't have to
rename their env.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Env vars consulted, in priority order. The first non-empty value wins.
_ENV_VARS: tuple[str, ...] = (
    "DECEPTICON_REASONING_EFFORT",
    "STRIX_REASONING_EFFORT",
)

# Provider knobs we know how to forward. Anthropic + OpenAI Reasoning
# (o-series, gpt-5.x) consume ``reasoning_effort`` as a top-level param;
# DeepSeek thinking-mode consumes it via ``extra_body``. Both are kept
# in :class:`EffortProfile` so the agent-init shim can apply both shapes.
EFFORT_LEVELS: tuple[str, ...] = ("quick", "standard", "deep")


@dataclass(frozen=True)
class EffortProfile:
    """Bundle of LLM kwargs for a given reasoning effort.

    Attributes:
        level:                Canonical name (``quick``/``standard``/``deep``).
        temperature_override: When non-None, replaces the per-agent temperature.
        max_tokens_override:  When non-None, replaces the per-agent max_tokens.
        reasoning_effort:     OpenAI / Anthropic ``reasoning_effort`` value
                              (``low``/``medium``/``high``) or None to skip.
        extra_body_overrides: Keys merged into the model's ``extra_body``.
    """

    level: str
    temperature_override: float | None = None
    max_tokens_override: int | None = None
    reasoning_effort: str | None = None
    extra_body_overrides: dict[str, Any] = field(default_factory=dict)


_PROFILES: dict[str, EffortProfile] = {
    "quick": EffortProfile(
        level="quick",
        temperature_override=0.1,
        max_tokens_override=2048,
        reasoning_effort="low",
        extra_body_overrides={"thinking": {"type": "disabled"}},
    ),
    "standard": EffortProfile(level="standard"),
    "deep": EffortProfile(
        level="deep",
        temperature_override=0.7,
        max_tokens_override=16384,
        reasoning_effort="high",
        extra_body_overrides={"thinking": {"type": "enabled", "budget_tokens": 16000}},
    ),
}


# Aliases for ergonomics — Strix uses ``high``/``medium``/``low``; CLI users
# might type ``fast`` or ``thorough``. Map them onto our canonical names.
_ALIASES: dict[str, str] = {
    "low": "quick",
    "fast": "quick",
    "medium": "standard",
    "default": "standard",
    "normal": "standard",
    "high": "deep",
    "thorough": "deep",
    "max": "deep",
    "yolo": "deep",
}


def normalise_effort(value: str | None) -> str | None:
    """Map a free-form effort string to a canonical level or ``None``.

    Returns ``None`` when ``value`` is empty or unrecognised so the caller
    can fall through to the default behaviour without raising.
    """
    if not value:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v in EFFORT_LEVELS:
        return v
    return _ALIASES.get(v)


def get_effort_level(default: str = "standard") -> str:
    """Resolve the active effort level from environment or fallback.

    Args:
        default: Returned when neither env var is set or the value cannot
            be parsed. Must itself be a valid level.
    """
    if default not in EFFORT_LEVELS:
        raise ValueError(f"default must be one of {EFFORT_LEVELS}, got {default!r}")
    for var in _ENV_VARS:
        canonical = normalise_effort(os.environ.get(var))
        if canonical:
            return canonical
    return default


def get_profile(level: str | None = None) -> EffortProfile:
    """Return the :class:`EffortProfile` for ``level`` (or the env-resolved level)."""
    canonical = normalise_effort(level) or get_effort_level()
    return _PROFILES.get(canonical, _PROFILES["standard"])


def effort_kwargs(level: str | None = None) -> dict[str, Any]:
    """Return a kwargs dict suitable for ``ChatOpenAI(...)`` construction.

    Only includes keys the profile actually wants to override — callers
    can ``**``-merge it on top of their own defaults.
    """
    p = get_profile(level)
    out: dict[str, Any] = {}
    if p.temperature_override is not None:
        out["temperature"] = p.temperature_override
    if p.max_tokens_override is not None:
        out["max_tokens"] = p.max_tokens_override
    if p.reasoning_effort is not None:
        out["reasoning_effort"] = p.reasoning_effort
    if p.extra_body_overrides:
        out["extra_body"] = dict(p.extra_body_overrides)
    return out


def apply_effort_to_chat_model(model: Any, level: str | None = None) -> Any:
    """Mutate a ChatOpenAI-like instance in place with effort overrides.

    The factory builds the model with sensible per-tier defaults; this hook
    lets the agent layer (or the launcher's ``--effort`` flag) escalate /
    soften that on a per-run basis without rebuilding the factory.

    Best-effort: unknown attributes are skipped so a ChatModel that doesn't
    expose ``temperature`` or ``extra_body`` won't crash.
    """
    if model is None:
        return model
    p = get_profile(level)
    if p.level == "standard":
        return model  # nothing to override
    if p.temperature_override is not None and hasattr(model, "temperature"):
        try:
            object.__setattr__(model, "temperature", p.temperature_override)
        except Exception as exc:  # noqa: BLE001
            log.debug("effort: temperature override skipped (%s)", exc)
    if p.max_tokens_override is not None and hasattr(model, "max_tokens"):
        try:
            object.__setattr__(model, "max_tokens", p.max_tokens_override)
        except Exception as exc:  # noqa: BLE001
            log.debug("effort: max_tokens override skipped (%s)", exc)
    if p.reasoning_effort is not None and hasattr(model, "reasoning_effort"):
        try:
            object.__setattr__(model, "reasoning_effort", p.reasoning_effort)
        except Exception as exc:  # noqa: BLE001
            log.debug("effort: reasoning_effort override skipped (%s)", exc)
    if p.extra_body_overrides and hasattr(model, "extra_body"):
        try:
            existing = getattr(model, "extra_body", None) or {}
            merged = {**existing, **p.extra_body_overrides}
            object.__setattr__(model, "extra_body", merged)
        except Exception as exc:  # noqa: BLE001
            log.debug("effort: extra_body merge skipped (%s)", exc)
    return model


__all__ = [
    "EFFORT_LEVELS",
    "EffortProfile",
    "apply_effort_to_chat_model",
    "effort_kwargs",
    "get_effort_level",
    "get_profile",
    "normalise_effort",
]
