"""Tests for the reasoning-effort knob."""

from __future__ import annotations

import pytest

from decepticon.llm.effort import (
    EFFORT_LEVELS,
    EffortProfile,
    apply_effort_to_chat_model,
    effort_kwargs,
    get_effort_level,
    get_profile,
    normalise_effort,
)

# ── normalisation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("quick", "quick"),
        ("Quick", "quick"),
        (" QUICK ", "quick"),
        ("standard", "standard"),
        ("deep", "deep"),
        ("low", "quick"),
        ("fast", "quick"),
        ("medium", "standard"),
        ("default", "standard"),
        ("normal", "standard"),
        ("high", "deep"),
        ("thorough", "deep"),
        ("max", "deep"),
        ("yolo", "deep"),
        ("", None),
        ("   ", None),
        (None, None),
        ("nonsense", None),
    ],
    ids=lambda v: repr(v),
)
def test_normalise_effort(raw, expected):
    assert normalise_effort(raw) == expected


# ── env resolution ────────────────────────────────────────────────


def test_get_effort_level_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DECEPTICON_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("STRIX_REASONING_EFFORT", raising=False)
    assert get_effort_level() == "standard"
    assert get_effort_level(default="deep") == "deep"


def test_get_effort_level_reads_decepticon_env(monkeypatch):
    monkeypatch.setenv("DECEPTICON_REASONING_EFFORT", "deep")
    monkeypatch.delenv("STRIX_REASONING_EFFORT", raising=False)
    assert get_effort_level() == "deep"


def test_get_effort_level_reads_strix_alias(monkeypatch):
    monkeypatch.delenv("DECEPTICON_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("STRIX_REASONING_EFFORT", "high")
    assert get_effort_level() == "deep"


def test_get_effort_level_decepticon_wins_over_strix(monkeypatch):
    monkeypatch.setenv("DECEPTICON_REASONING_EFFORT", "quick")
    monkeypatch.setenv("STRIX_REASONING_EFFORT", "deep")
    assert get_effort_level() == "quick"


def test_get_effort_level_invalid_default_rejected(monkeypatch):
    monkeypatch.delenv("DECEPTICON_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("STRIX_REASONING_EFFORT", raising=False)
    with pytest.raises(ValueError, match="default must be one of"):
        get_effort_level(default="bogus")


# ── profile lookup ────────────────────────────────────────────────


def test_profile_levels_cover_all_constants():
    for lvl in EFFORT_LEVELS:
        p = get_profile(lvl)
        assert isinstance(p, EffortProfile)
        assert p.level == lvl


def test_profile_standard_has_no_overrides():
    p = get_profile("standard")
    assert p.temperature_override is None
    assert p.max_tokens_override is None
    assert p.reasoning_effort is None
    assert p.extra_body_overrides == {}


def test_profile_quick_has_low_overrides():
    p = get_profile("quick")
    assert p.temperature_override == 0.1
    assert p.max_tokens_override == 2048
    assert p.reasoning_effort == "low"
    assert p.extra_body_overrides["thinking"]["type"] == "disabled"


def test_profile_deep_has_high_overrides():
    p = get_profile("deep")
    assert p.temperature_override == 0.7
    assert p.max_tokens_override == 16384
    assert p.reasoning_effort == "high"
    assert p.extra_body_overrides["thinking"]["type"] == "enabled"
    assert p.extra_body_overrides["thinking"]["budget_tokens"] == 16000


def test_profile_unknown_level_falls_back_to_standard():
    p = get_profile("not-a-level")
    assert p.level == "standard"


# ── kwargs serialisation ──────────────────────────────────────────


def test_effort_kwargs_standard_returns_empty():
    assert effort_kwargs("standard") == {}


def test_effort_kwargs_quick_includes_all_fields():
    out = effort_kwargs("quick")
    assert out["temperature"] == 0.1
    assert out["max_tokens"] == 2048
    assert out["reasoning_effort"] == "low"
    assert out["extra_body"] == {"thinking": {"type": "disabled"}}


def test_effort_kwargs_deep_includes_all_fields():
    out = effort_kwargs("deep")
    assert out["temperature"] == 0.7
    assert out["max_tokens"] == 16384
    assert out["reasoning_effort"] == "high"
    assert out["extra_body"]["thinking"]["budget_tokens"] == 16000


def test_effort_kwargs_with_alias_resolves():
    assert effort_kwargs("high") == effort_kwargs("deep")
    assert effort_kwargs("low") == effort_kwargs("quick")


# ── runtime model patching ────────────────────────────────────────


class _FakeModel:
    """Minimal stand-in for a ChatOpenAI instance."""

    def __init__(self) -> None:
        self.temperature = 0.5
        self.max_tokens = 4096
        self.reasoning_effort: str | None = None
        self.extra_body: dict | None = None


def test_apply_effort_standard_is_noop():
    m = _FakeModel()
    apply_effort_to_chat_model(m, "standard")
    assert m.temperature == 0.5
    assert m.max_tokens == 4096
    assert m.reasoning_effort is None


def test_apply_effort_quick_overrides_all_fields():
    m = _FakeModel()
    apply_effort_to_chat_model(m, "quick")
    assert m.temperature == 0.1
    assert m.max_tokens == 2048
    assert m.reasoning_effort == "low"
    assert m.extra_body == {"thinking": {"type": "disabled"}}


def test_apply_effort_deep_overrides_all_fields():
    m = _FakeModel()
    apply_effort_to_chat_model(m, "deep")
    assert m.temperature == 0.7
    assert m.max_tokens == 16384
    assert m.reasoning_effort == "high"
    assert m.extra_body == {"thinking": {"type": "enabled", "budget_tokens": 16000}}


def test_apply_effort_merges_existing_extra_body():
    m = _FakeModel()
    m.extra_body = {"foo": "bar"}
    apply_effort_to_chat_model(m, "deep")
    assert m.extra_body["foo"] == "bar"
    assert m.extra_body["thinking"]["type"] == "enabled"


def test_apply_effort_ignores_missing_attributes():
    """Models without the override-able attributes are left unchanged."""

    class _Bare:
        pass

    bare = _Bare()
    # Should not raise even though the bare model has none of the attrs.
    apply_effort_to_chat_model(bare, "deep")


def test_apply_effort_uses_env_when_level_omitted(monkeypatch):
    monkeypatch.setenv("DECEPTICON_REASONING_EFFORT", "deep")
    m = _FakeModel()
    apply_effort_to_chat_model(m)
    assert m.temperature == 0.7


def test_apply_effort_returns_model_for_chaining():
    m = _FakeModel()
    out = apply_effort_to_chat_model(m, "quick")
    assert out is m


def test_apply_effort_handles_none_model():
    """Defensive: ``apply_effort_to_chat_model(None)`` must not raise."""
    assert apply_effort_to_chat_model(None, "deep") is None
