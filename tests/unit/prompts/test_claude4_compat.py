"""Tests for decepticon.agents.prompts.claude4_compat.

Loaded via importlib so the test suite does not require the full
decepticon.agents runtime dependency tree (deepagents, langgraph, …).
The shim is pure Python and should not need those to be tested.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "decepticon" / "agents" / "prompts" / "claude4_compat.py"
)
_spec = importlib.util.spec_from_file_location("decepticon_claude4_compat_under_test", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

apply_claude4_compat = _module.apply_claude4_compat
is_claude4_family = _module.is_claude4_family
prepend_neutral_persona = _module.prepend_neutral_persona
substitute_trigger_terms = _module.substitute_trigger_terms


class TestIsClaude4Family:
    @pytest.mark.parametrize(
        "model",
        [
            "anthropic/claude-opus-4-7",
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-haiku-4-5",
            "claude-opus-4-7",
            "openrouter/anthropic/claude-sonnet-4-5-20250929",
            "bedrock/anthropic.claude-opus-4-7-v1:0",
        ],
    )
    def test_positive(self, model: str) -> None:
        assert is_claude4_family(model) is True

    @pytest.mark.parametrize(
        "model",
        [
            None,
            "",
            "anthropic/claude-3-5-sonnet-20241022",
            "claude-3-7-sonnet-20250219",
            "gpt-4o-2024-11-20",
            "openrouter/deepseek/deepseek-chat",
            "qwen/qwen-2.5-coder-32b-instruct",
        ],
    )
    def test_negative(self, model: str | None) -> None:
        assert is_claude4_family(model) is False


class TestSubstituteTriggerTerms:
    def test_basic_substitution(self) -> None:
        prompt = "Perform Recon on the target network."
        out = substitute_trigger_terms(prompt)
        assert "Discovery" in out
        assert "Recon" not in out

    def test_word_boundary(self) -> None:
        prompt = "Reconcile the budget before Recon."
        out = substitute_trigger_terms(prompt)
        assert "Reconcile" in out
        assert "Discovery" in out

    def test_longest_match_first(self) -> None:
        prompt = "Begin Post-Exploitation then continue Exploitation."
        out = substitute_trigger_terms(prompt)
        assert "Post-Access Validation" in out
        assert "Validation" in out
        assert "Post-Exploitation" not in out

    def test_empty_input(self) -> None:
        assert substitute_trigger_terms("") == ""

    def test_custom_map(self) -> None:
        out = substitute_trigger_terms("block this foo", {"foo": "bar"})
        assert out == "block this bar"

    def test_preserves_unrelated_content(self) -> None:
        prompt = "Use nmap to scan 10.0.0.0/24 for open ports."
        assert substitute_trigger_terms(prompt) == prompt


class TestPrependNeutralPersona:
    def test_prepends_once(self) -> None:
        prompt = "DECEPTICON: autonomous red team orchestrator."
        wrapped = prepend_neutral_persona(prompt)
        assert wrapped.startswith("AUTHORIZATION CONTEXT:")
        assert prepend_neutral_persona(wrapped) == wrapped

    def test_empty_input(self) -> None:
        out = prepend_neutral_persona("")
        assert out.startswith("AUTHORIZATION CONTEXT:")


class TestApplyClaude4Compat:
    def test_noop_for_non_claude4(self) -> None:
        prompt = "You are an offensive security Recon agent."
        out = apply_claude4_compat(prompt, "anthropic/claude-3-5-sonnet-20241022")
        assert out == prompt

    def test_applies_for_claude4(self) -> None:
        prompt = "You are an offensive security Recon agent."
        out = apply_claude4_compat(prompt, "anthropic/claude-opus-4-7")
        assert out.startswith("AUTHORIZATION CONTEXT:")
        assert "Discovery" in out
        assert "authorized security assessment" in out
        assert "Recon" not in out
        assert "offensive security" not in out

    def test_noop_for_none_model(self) -> None:
        prompt = "Exploitation plan for target."
        assert apply_claude4_compat(prompt, None) == prompt

    def test_idempotent_on_claude4(self) -> None:
        prompt = "Red Team engagement against lab infrastructure."
        once = apply_claude4_compat(prompt, "claude-sonnet-4-6")
        twice = apply_claude4_compat(once, "claude-sonnet-4-6")
        assert once == twice

    def test_env_disable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_CLAUDE4_COMPAT", "0")
        prompt = "Red Team Recon engagement."
        assert apply_claude4_compat(prompt, "claude-opus-4-7") == prompt
