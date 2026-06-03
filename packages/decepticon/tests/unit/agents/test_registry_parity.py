"""Anti-drift guards for the agent registries.

Three independent registries must stay in lock-step or an agent silently
half-wires: the ``decepticon.subagents`` entry-point group (what the
orchestrator can dispatch), the LangGraph manifests (what can be served
as a standalone graph), and the role tables in ``decepticon_core``
(slots + model tiers). The ``phisher`` / ``mobile_operator`` /
``wireless_operator`` agents shipped registered as subagents but absent
from ``graph_registry`` / ``langgraph.json`` — these tests would have
failed on that drift; keep them green.
"""

from __future__ import annotations

import json
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from decepticon.graph_registry import BUILTIN_GRAPHS, STANDARD_GRAPHS
from decepticon_core.contracts.slots import SLOTS_PER_ROLE
from decepticon_core.types.llm import AGENT_TIERS


def _find_repo_file(name: str) -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(name)


def _subagent_entry_point_names() -> list[str]:
    return sorted(ep.name for ep in entry_points(group="decepticon.subagents"))


def test_every_registered_subagent_has_a_graph():
    """Each ``decepticon.subagents`` entry point must have a built-in graph.

    Catches the original defect: a specialist registered as a dispatchable
    subagent but missing from ``graph_registry`` (so it can never be served
    as a standalone LangGraph assistant).
    """
    missing = [name for name in _subagent_entry_point_names() if name not in BUILTIN_GRAPHS]
    assert not missing, f"subagents without a built-in graph: {missing}"


def test_every_slot_role_has_a_model_tier():
    """Every role in ``SLOTS_PER_ROLE`` must have an ``AGENT_TIERS`` entry.

    ``_resolve_tier`` does ``AGENT_TIERS[role]`` — a missing tier is a hard
    KeyError the first time the agent's model is built.
    """
    missing = sorted(set(SLOTS_PER_ROLE) - set(AGENT_TIERS))
    assert not missing, f"roles with slots but no model tier: {missing}"


def test_langgraph_manifest_covers_standard_graphs():
    """The shipped ``langgraph.json`` must list every standard graph."""
    manifest = json.loads(_find_repo_file("langgraph.json").read_text(encoding="utf-8"))
    served = set(manifest["graphs"])
    missing = sorted(set(STANDARD_GRAPHS) - served)
    assert not missing, f"standard graphs absent from langgraph.json: {missing}"


@pytest.mark.parametrize(
    "role",
    ["phisher", "mobile_operator", "wireless_operator", "osint_operator", "iot_operator"],
)
def test_known_specialists_fully_wired(role):
    """Spot-check the specialists this guard was introduced for."""
    assert role in SLOTS_PER_ROLE
    assert role in AGENT_TIERS
    assert role in STANDARD_GRAPHS
    assert role in _subagent_entry_point_names()
