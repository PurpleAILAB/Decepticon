"""Wiring tests for the Defender standard agent.

PR3 gives the previously-orphaned ``DEFENSE_TOOLS`` (Sigma/YARA → SIEM/EDR push)
a real consumer. These pin that contract: the push surface reaches the agent,
every push tool sits behind the HITL approval gate, and the role is registered
end-to-end (slots, tiers, graph manifests, export) as a no-bash agent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from decepticon.agents import build
from decepticon.agents.standard import defender as agent_mod
from decepticon.middleware.hitl import DEFAULT_HIGH_IMPACT_POLICY
from decepticon.tools.defense import DEFENSE_TOOLS
from decepticon_core.contracts.slots import SLOTS_PER_ROLE, MiddlewareSlot

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PUSH_PREFIXES = ("sigma_to", "yara_to")


def test_defense_tools_wired_into_defender() -> None:
    """The orphaned-tools fix: every DEFENSE_TOOLS tool now reaches the agent."""
    names = set(agent_mod._STANDARD_TOOLS)
    assert {tool.name for tool in DEFENSE_TOOLS} <= names
    assert {"kg_query", "kg_neighbors", "kg_stats", "kg_add_node"} <= names
    # No attack surface — detection deployment is HTTP-only.
    assert "bash" not in names


def test_siem_push_tools_are_hitl_gated() -> None:
    """Every Sigma/YARA push the Defender can call must hit the approval gate."""
    push_tools = [name for name in agent_mod._STANDARD_TOOLS if name.startswith(_PUSH_PREFIXES)]
    assert push_tools  # sanity: the Defender actually exposes push tools
    patterns = [
        re.compile(rule.tool_pattern) for rule in DEFAULT_HIGH_IMPACT_POLICY if rule.tool_pattern
    ]
    for name in push_tools:
        assert any(p.match(name) for p in patterns), f"{name} is not HITL-gated"


def test_role_slots_are_engagement_aware_hitl_no_bash() -> None:
    slots = SLOTS_PER_ROLE["defender"]
    assert MiddlewareSlot.HITL_APPROVAL in slots  # writes to customer SIEM/EDR
    assert MiddlewareSlot.ENGAGEMENT_CONTEXT in slots  # needs the eng slug prefix
    assert MiddlewareSlot.SANDBOX_NOTIFICATION not in slots  # no bash


def test_build_tools_resolves_role_with_push_surface() -> None:
    tools = build.build_tools(role="defender", standard_tools=agent_mod._STANDARD_TOOLS)
    names = {t.name for t in tools}
    assert "sigma_to_sentinel_analyticrule" in names
    assert "bash" not in names


def test_subagent_spec_targets_orchestrator() -> None:
    spec = agent_mod.SUBAGENT_SPEC
    assert spec.name == "defender"
    assert spec.factory is agent_mod.create_defender_agent
    assert spec.parent_agents == ("decepticon",)
    assert spec.bundle == "standard"


def test_graph_manifests_register_defender() -> None:
    langgraph = json.loads((_REPO_ROOT / "langgraph.json").read_text(encoding="utf-8"))
    assert (
        langgraph["graphs"]["defender"]
        == "./packages/decepticon/decepticon/agents/standard/defender.py:graph"
    )
    from decepticon.graph_registry import STANDARD_GRAPHS

    assert "defender" in STANDARD_GRAPHS


def test_defender_published_as_decepticon_subagent() -> None:
    """Without a ``decepticon.subagents`` entry-point the orchestrator can never
    delegate to the Defender (graph-served but not discoverable). Parsed from
    pyproject so it is independent of editable-install metadata refresh."""
    import tomllib

    pyproject = _REPO_ROOT / "packages" / "decepticon" / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    subagents = data["project"]["entry-points"]["decepticon.subagents"]
    assert subagents.get("defender") == "decepticon.agents.standard.defender:SUBAGENT_SPEC"
