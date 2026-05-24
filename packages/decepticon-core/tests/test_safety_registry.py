"""SafetyRegistry enforcement — closes spec §16.4 #4 additive-only.

Verifies the registry merges plugin contributions with the OSS
baseline at lookup time, and that the additive-only contract holds:
plugins can extend the safety-critical set but cannot remove safety
on OSS-declared names.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from decepticon_core.contracts.contributions import SafetyDeclaration
from decepticon_core.registry import SafetyRegistry


@pytest.fixture(autouse=True)
def _reset_safety_registry() -> Iterator[None]:
    """Each test starts with no plugin registrations."""
    SafetyRegistry.reset()
    yield
    SafetyRegistry.reset()


def test_baseline_unaffected_when_no_plugin_registered() -> None:
    oss_baseline = frozenset({"ask_user_question", "complete_engagement_planning"})
    merged = SafetyRegistry.merged_critical_tools(oss_baseline)
    assert merged == oss_baseline


def test_plugin_declaration_adds_to_merged_set() -> None:
    SafetyRegistry.register(
        SafetyDeclaration(tools=("my_dangerous_tool",)),
        owner="my-plugin",
    )
    merged = SafetyRegistry.merged_critical_tools(frozenset({"ask_user_question"}))
    assert "my_dangerous_tool" in merged
    assert "ask_user_question" in merged


def test_additive_only_cannot_remove_oss_baseline() -> None:
    """Spec §16.4 #4 — there is intentionally no API to remove OSS names.

    Even after a plugin registers (and even after ``reset()``), the
    baseline always survives because it's passed in at lookup time
    rather than stored.
    """
    SafetyRegistry.register(
        SafetyDeclaration(tools=("my_dangerous_tool",)),
        owner="my-plugin",
    )
    SafetyRegistry.reset()
    oss_baseline = frozenset({"ask_user_question"})
    assert SafetyRegistry.merged_critical_tools(oss_baseline) == oss_baseline


def test_middleware_declarations_separate_from_tools() -> None:
    SafetyRegistry.register(
        SafetyDeclaration(
            tools=("tool_a",),
            middleware=("slot_b",),
        ),
        owner="plug",
    )
    oss_slots = frozenset({"engagement-context"})
    oss_tools = frozenset({"ask_user_question"})
    assert SafetyRegistry.merged_critical_slots(oss_slots) == frozenset(
        {"engagement-context", "slot_b"}
    )
    assert SafetyRegistry.merged_critical_tools(oss_tools) == frozenset(
        {"ask_user_question", "tool_a"}
    )


def test_plugin_tools_owner_attribution() -> None:
    SafetyRegistry.register(SafetyDeclaration(tools=("t1",)), owner="pkg-a")
    SafetyRegistry.register(SafetyDeclaration(tools=("t2",)), owner="pkg-b")
    pairs = dict(SafetyRegistry.plugin_tools())
    assert pairs == {"t1": "pkg-a", "t2": "pkg-b"}


def test_check_safety_gate_consumes_registry() -> None:
    """End-to-end: a plugin-declared tool name is rejected by
    ``_check_safety_gate`` without the env override.

    This is the integration that closes the spec drift the
    security review flagged — registry-only data participates in
    the live safety gate.
    """
    from decepticon.agents.build import SafetyOverrideViolation, _check_safety_gate

    SafetyRegistry.register(
        SafetyDeclaration(tools=("plugin_special_tool",)),
        owner="my-plugin",
    )

    with pytest.raises(SafetyOverrideViolation, match=r"plugin_special_tool"):
        _check_safety_gate(
            role="recon",
            mw_replace={},
            mw_disable=frozenset(),
            tool_replace={},
            tool_disable=frozenset({"plugin_special_tool"}),
        )
