"""Plugin override + safety-gate tests for the agent-assembly pipeline.

These pin the contract the 16 agent factories rely on:

  - ``assemble_middleware`` / ``assemble_tools`` apply plugin entry-point
    overrides AND explicit kwargs, with explicit winning on conflict.
  - ``resolve_prompt_overrides`` merges plugin + explicit prompt patches.
  - Safety-critical slot/tool overrides raise ``SafetyOverrideViolation``
    unless ``DECEPTICON_ALLOW_SAFETY_OVERRIDES=1`` is in the environment.
  - ``PluginBundle.matches_role`` honors ``applies_to_roles`` scoping.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from decepticon.agents import assembly
from decepticon.agents.middleware_slots import MiddlewareSlot
from decepticon import plugin_loader
from decepticon.plugin_loader import PluginBundle


class _FakeEntryPoint:
    """Stand-in for ``importlib.metadata.EntryPoint`` used in bundle tests."""

    def __init__(self, name: str, value: str, loaded):
        self.name = name
        self.value = value
        self._loaded = loaded

    def load(self):
        return self._loaded


# ── PluginBundle.matches_role ────────────────────────────────────────


def test_plugin_bundle_unrestricted_matches_every_role():
    bundle = PluginBundle(items=())
    assert bundle.matches_role("decepticon")
    assert bundle.matches_role("any-future-role")


def test_plugin_bundle_applies_to_roles_filter():
    bundle = PluginBundle(applies_to_roles=("recon", "exploit"))
    assert bundle.matches_role("recon")
    assert bundle.matches_role("exploit")
    assert not bundle.matches_role("soundwave")


# ── _iter_override_bundles discovery ─────────────────────────────────


def test_iter_override_bundles_yields_role_scoped_bundles_only():
    saas_recon = PluginBundle(applies_to_roles=("recon",))
    saas_all = PluginBundle()
    eps = [
        _FakeEntryPoint("saas-recon", "saas:recon_bundle", saas_recon),
        _FakeEntryPoint("saas-all", "saas:all_bundle", saas_all),
    ]
    with patch.object(assembly, "entry_points", return_value=eps):
        for_recon = list(assembly._iter_override_bundles("recon"))
        for_exploit = list(assembly._iter_override_bundles("exploit"))

    assert saas_recon in for_recon
    assert saas_all in for_recon
    # saas_recon is filtered out for exploit
    assert saas_all in for_exploit
    assert saas_recon not in for_exploit


def test_iter_override_bundles_skips_non_pluginbundle_loads():
    """Entry-points returning anything other than a PluginBundle (or a
    factory thereof) are skipped silently — protects against
    misregistered entry-points."""
    not_a_bundle = MagicMock()  # plain mock, not a PluginBundle
    eps = [_FakeEntryPoint("bad", "x:y", not_a_bundle)]
    with patch.object(assembly, "entry_points", return_value=eps):
        assert list(assembly._iter_override_bundles("recon")) == []


# ── Override resolution (plugin + explicit merge) ────────────────────


def test_resolve_overrides_explicit_wins_over_plugin():
    """When a plugin and the explicit kwarg both touch the same tool
    name, the explicit kwarg replacement is the one assembled."""
    plugin_tool = MagicMock(name="plugin_tool")
    explicit_tool = MagicMock(name="explicit_tool")
    bundle = PluginBundle(
        replaced_tools={"ask_user_question": plugin_tool},
    )
    eps = [_FakeEntryPoint("saas", "saas:bundle", bundle)]
    with patch.object(assembly, "entry_points", return_value=eps):
        resolved = assembly._resolve_overrides(
            role="soundwave",
            explicit_middleware_replace=None,
            explicit_middleware_disable=None,
            explicit_tool_replace={"ask_user_question": explicit_tool},
            explicit_tool_disable=None,
            explicit_prompt=None,
        )
    assert resolved.tool_replace["ask_user_question"] is explicit_tool


def test_resolve_overrides_merges_disable_from_plugin_and_explicit():
    bundle = PluginBundle(disabled_tools=("plugin_tool",))
    eps = [_FakeEntryPoint("saas", "saas:bundle", bundle)]
    with patch.object(assembly, "entry_points", return_value=eps):
        resolved = assembly._resolve_overrides(
            role="recon",
            explicit_middleware_replace=None,
            explicit_middleware_disable=None,
            explicit_tool_replace=None,
            explicit_tool_disable={"explicit_tool"},
            explicit_prompt=None,
        )
    assert resolved.tool_disable == frozenset({"plugin_tool", "explicit_tool"})


# ── Safety gate ──────────────────────────────────────────────────────


def test_safety_gate_blocks_disabling_critical_tool(monkeypatch):
    """``ask_user_question`` is safety-critical — disabling it without
    the env gate raises."""
    monkeypatch.delenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", raising=False)
    with pytest.raises(assembly.SafetyOverrideViolation):
        assembly._check_safety_gate(
            role="soundwave",
            mw_replace={},
            mw_disable=frozenset(),
            tool_replace={},
            tool_disable=frozenset({"ask_user_question"}),
        )


def test_safety_gate_blocks_replacing_critical_slot(monkeypatch):
    """``engagement-context`` carries RoE scope — replacing it without
    the env gate raises."""
    monkeypatch.delenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", raising=False)
    with pytest.raises(assembly.SafetyOverrideViolation):
        assembly._check_safety_gate(
            role="recon",
            mw_replace={"engagement-context": lambda **_: object()},
            mw_disable=frozenset(),
            tool_replace={},
            tool_disable=frozenset(),
        )


def test_safety_gate_env_bypass(monkeypatch):
    """``DECEPTICON_ALLOW_SAFETY_OVERRIDES=1`` lets safety-critical
    overrides through without raising."""
    monkeypatch.setenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", "1")
    # Should NOT raise
    assembly._check_safety_gate(
        role="soundwave",
        mw_replace={"engagement-context": lambda **_: object()},
        mw_disable=frozenset(),
        tool_replace={},
        tool_disable=frozenset({"ask_user_question"}),
    )


def test_safety_gate_allows_non_critical_overrides(monkeypatch):
    """A non-critical slot like ``prompt-caching`` is safely disable-able
    without the env gate."""
    monkeypatch.delenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", raising=False)
    # Should NOT raise
    assembly._check_safety_gate(
        role="soundwave",
        mw_replace={},
        mw_disable=frozenset({"prompt-caching"}),
        tool_replace={},
        tool_disable=frozenset(),
    )


# ── assemble_middleware end-to-end ───────────────────────────────────


def test_assemble_middleware_unknown_role_raises():
    """Unknown role = unset slot mapping; assembler refuses rather than
    silently building an empty stack."""
    with pytest.raises(KeyError, match="unknown role"):
        assembly.assemble_middleware(
            role="not-a-real-role",
            backend=MagicMock(),
            llm=MagicMock(),
        )


# Real OSS slot factories instantiate middleware that does deep runtime
# checks (``create_summarization_middleware`` calls ``model.profile`` on
# the BaseChatModel, etc.). To keep these assembly tests fast and free
# of real model wiring, we disable the heavyweight slots that need a
# live chat model and only exercise the lighter-weight slots that touch
# backend/sandbox. The override semantics (replace/disable) are the
# same on every slot — verifying SKILLS + PROMPT_CACHING is sufficient.
_HEAVY_SLOTS: set[MiddlewareSlot] = {MiddlewareSlot.SUMMARIZATION}


def test_assemble_middleware_applies_plugin_slot_replacement(monkeypatch):
    """Plugin's ``replaced_middleware`` substitutes the slot factory."""
    monkeypatch.setenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", "1")
    sentinel = MagicMock(name="custom_skills_mw")

    def custom_factory(**_):
        return sentinel

    bundle = PluginBundle(replaced_middleware={"skills": custom_factory})
    eps = [_FakeEntryPoint("saas", "saas:bundle", bundle)]

    with patch.object(assembly, "entry_points", return_value=eps):
        with patch.object(plugin_loader, "entry_points", return_value=[]):
            result = assembly.assemble_middleware(
                role="soundwave",
                backend=MagicMock(),
                llm=MagicMock(),
                fallback_models=None,
                disabled_slots=_HEAVY_SLOTS,
            )
    assert sentinel in result


def test_assemble_middleware_disable_skips_slot(monkeypatch):
    """An explicit ``disabled_slots`` skip drops the slot's instance from
    the returned list."""
    monkeypatch.delenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", raising=False)

    with patch.object(assembly, "entry_points", return_value=[]):
        with patch.object(plugin_loader, "entry_points", return_value=[]):
            with_caching = assembly.assemble_middleware(
                role="soundwave",
                backend=MagicMock(),
                llm=MagicMock(),
                fallback_models=None,
                disabled_slots=_HEAVY_SLOTS,
            )
            without_caching = assembly.assemble_middleware(
                role="soundwave",
                backend=MagicMock(),
                llm=MagicMock(),
                fallback_models=None,
                disabled_slots=_HEAVY_SLOTS | {MiddlewareSlot.PROMPT_CACHING},
            )
    assert len(without_caching) == len(with_caching) - 1


# ── assemble_tools end-to-end ────────────────────────────────────────


def test_assemble_tools_dict_baseline_preserved():
    """A dict baseline survives plugin/explicit no-op walks."""
    baseline = {"a": MagicMock(name="a"), "b": MagicMock(name="b")}
    with patch.object(assembly, "entry_points", return_value=[]):
        with patch.object(plugin_loader, "entry_points", return_value=[]):
            result = assembly.assemble_tools(role="soundwave", standard_tools=baseline)
    # Order preserved, both present.
    assert result == [baseline["a"], baseline["b"]]


def test_assemble_tools_explicit_disable_drops_name(monkeypatch):
    monkeypatch.setenv("DECEPTICON_ALLOW_SAFETY_OVERRIDES", "1")
    baseline = {"keep": MagicMock(name="keep"), "drop": MagicMock(name="drop")}
    with patch.object(assembly, "entry_points", return_value=[]):
        with patch.object(plugin_loader, "entry_points", return_value=[]):
            result = assembly.assemble_tools(
                role="soundwave",
                standard_tools=baseline,
                disabled_tools={"drop"},
            )
    assert baseline["keep"] in result
    assert baseline["drop"] not in result


def test_assemble_tools_plugin_replaces_by_name():
    """``PluginBundle.replaced_tools`` substitutes a baseline tool by name."""
    baseline = {"primary": MagicMock(name="primary")}
    replacement = MagicMock(name="replacement")
    bundle = PluginBundle(replaced_tools={"primary": replacement})
    eps = [_FakeEntryPoint("saas", "saas:bundle", bundle)]
    with patch.object(assembly, "entry_points", return_value=eps):
        with patch.object(plugin_loader, "entry_points", return_value=[]):
            result = assembly.assemble_tools(role="soundwave", standard_tools=baseline)
    assert replacement in result
    assert baseline["primary"] not in result


# ── Prompt override resolution ───────────────────────────────────────


def test_resolve_prompt_overrides_explicit_string_means_replace():
    with patch.object(assembly, "entry_points", return_value=[]):
        merged = assembly.resolve_prompt_overrides("soundwave", override="FULL")
    assert merged == {"replace": "FULL"}


def test_resolve_prompt_overrides_dict_keeps_prepend_and_append():
    with patch.object(assembly, "entry_points", return_value=[]):
        merged = assembly.resolve_prompt_overrides(
            "soundwave",
            override={"prepend": "<P>", "append": "<A>"},
        )
    assert merged == {"prepend": "<P>", "append": "<A>"}


def test_resolve_prompt_overrides_plugin_only():
    """When the explicit override is None, the plugin's prompt_overrides
    for that role come through."""
    bundle = PluginBundle(
        prompt_overrides={"soundwave": {"append": "<SAAS>"}},
    )
    eps = [_FakeEntryPoint("saas", "saas:bundle", bundle)]
    with patch.object(assembly, "entry_points", return_value=eps):
        merged = assembly.resolve_prompt_overrides("soundwave")
    assert merged == {"append": "<SAAS>"}
