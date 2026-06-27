from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PROMPTS = _REPO_ROOT / "packages/decepticon/decepticon/agents/prompts/standard"
_REVERSER_AGENT = _REPO_ROOT / "packages/decepticon/decepticon/agents/standard/reverser.py"

_REVERSER_SKILL = _REPO_ROOT / "packages/decepticon/decepticon/skills/standard/reverser/SKILL.md"


def test_orchestrator_dispatches_reverser_for_no_workload_triage() -> None:
    prompt = (_PROMPTS / "decepticon.md").read_text()

    assert "Basic triage / Radare2 work still goes to `reverser`" in prompt
    assert "only for Ghidra MCP / headless decompilation" in prompt
    assert 'Do NOT block binary triage just because `ops_start("reversing")` fails' in prompt


def test_reverser_prompt_has_radare2_fallback_path() -> None:
    prompt = (_PROMPTS / "reverser.md").read_text()

    assert "RADARE2" in prompt
    assert "bin_r2_script" in prompt
    assert "Radare2/r2" in prompt


def test_reverser_spec_advertises_basic_triage_without_workload() -> None:
    agent_src = _REVERSER_AGENT.read_text()

    assert "Radare2-assisted basic triage without the reversing workload" in agent_src


def test_reverser_skill_catalog_names_radare2_fallback() -> None:
    skill = _REVERSER_SKILL.read_text()

    assert "Radare2" in skill
    assert "bin_r2_script" in skill
