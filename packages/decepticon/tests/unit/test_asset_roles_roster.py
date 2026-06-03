"""Every asset-type routing role is a real subagent (or a known planning role)."""

from __future__ import annotations

import functools
from importlib.metadata import entry_points

from decepticon_core.plugin_loader import SUBAGENTS_GROUP
from decepticon_core.types import asset_types as at


@functools.cache
def _live_subagent_roles() -> set[str]:
    roles: set[str] = set()
    for ep in entry_points(group=SUBAGENTS_GROUP):
        spec = ep.load()  # loads the SUBAGENT_SPEC object; does NOT call the factory
        roles.add(spec.name)
    return roles


def test_catalog_agents_are_live_subagents():
    live = _live_subagent_roles()
    # Top-level orchestrator/planner agents: valid routing roles but never
    # registered under SUBAGENTS_GROUP and never used in catalog .agents today.
    non_subagent = {"decepticon", "soundwave"}
    referenced = {role for a in at.all() for role in a.agents}
    unknown = referenced - live - non_subagent
    assert not unknown, f"asset catalog references non-existent roles: {sorted(unknown)}"


def test_valid_agent_roles_constant_matches_reality():
    live = _live_subagent_roles()
    # We assert only live ⊆ VALID_AGENT_ROLES (a newly-registered subagent must
    # be added to the constant). The reverse is intentionally NOT asserted:
    # VALID_AGENT_ROLES is a deliberate superset — it also covers plugin-bundle
    # agents (scanner/exploiter/verifier/patcher/detector/vulnresearch) and
    # blue-team agents (blue_cell/defender) that register under separate bundles
    # and are not visible via this standard SUBAGENTS_GROUP enumeration.
    missing = live - at.VALID_AGENT_ROLES
    assert not missing, f"VALID_AGENT_ROLES is stale; add: {sorted(missing)}"
