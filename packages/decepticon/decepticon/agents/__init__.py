"""Decepticon agent registry.

Standard bundle: decepticon main agent + 16 official subagents + soundwave.
Plugins bundle: vulnresearch main agent + its 5 subagents (community-plugin
shape demonstrated from inside OSS). See decepticon/agents/plugins/__init__.py.

The agent ``create_*_agent`` factories are loaded on first access via
``__getattr__`` (PEP 562) so that ``from decepticon.agents import foo``
does NOT eagerly import all 25 subagent modules. Without this, a single
``import decepticon`` pays the cost of constructing every agent's
LLM stack, middleware, and pydantic model — ~25 s on a 199-package
dev venv. With it, the import is < 1 s and only the agents the
deployment actually uses are loaded (the decepticon orchestrator
and soundwave planner in the current mundAgent deployment, so
roughly 7-8 s saved on each langgraph process start).
"""

from __future__ import annotations

import importlib

# Mapping of public name → submodule path. The factories live in two
# sub-packages: ``standard`` (decepticon + 16 subagents + soundwave)
# and ``plugins`` (vulnresearch main + 5 subagents).
_LAZY_AGENTS: dict[str, str] = {
    # ── Standard bundle ─────────────────────────────────────────────
    "create_ad_operator_agent": "decepticon.agents.standard.ad_operator",
    "create_analyst_agent": "decepticon.agents.standard.analyst",
    "create_blue_cell_agent": "decepticon.agents.standard.blue_cell",
    "create_cloud_hunter_agent": "decepticon.agents.standard.cloud_hunter",
    "create_contract_auditor_agent": "decepticon.agents.standard.contract_auditor",
    "create_decepticon_agent": "decepticon.agents.standard.decepticon",
    "create_exploit_agent": "decepticon.agents.standard.exploit",
    "create_forensicator_agent": "decepticon.agents.standard.forensicator",
    "create_ics_operator_agent": "decepticon.agents.standard.ics_operator",
    "create_iot_operator_agent": "decepticon.agents.standard.iot_operator",
    "create_mobile_operator_agent": "decepticon.agents.standard.mobile_operator",
    "create_osint_operator_agent": "decepticon.agents.standard.osint_operator",
    "create_phisher_agent": "decepticon.agents.standard.phisher",
    "create_postexploit_agent": "decepticon.agents.standard.postexploit",
    "create_recon_agent": "decepticon.agents.standard.recon",
    "create_reverser_agent": "decepticon.agents.standard.reverser",
    "create_soundwave_agent": "decepticon.agents.standard.soundwave",
    "create_supply_chain_operator_agent": "decepticon.agents.standard.supply_chain_operator",
    "create_wireless_operator_agent": "decepticon.agents.standard.wireless_operator",
    # ── Plugins bundle (vulnresearch pipeline) ───────────────────────
    "create_detector_agent": "decepticon.agents.plugins.detector",
    "create_exploiter_agent": "decepticon.agents.plugins.exploiter",
    "create_patcher_agent": "decepticon.agents.plugins.patcher",
    "create_scanner_agent": "decepticon.agents.plugins.scanner",
    "create_verifier_agent": "decepticon.agents.plugins.verifier",
    "create_vulnresearch_agent": "decepticon.agents.plugins.vulnresearch",
}

__all__ = sorted(_LAZY_AGENTS)


def __getattr__(name: str):
    """Resolve a public factory name on first access.

    Imported lazily so that the import-time work for ``decepticon.agents``
    is just the dict above (a few KB) rather than the 25 agent
    factories. The factory handle is cached in the module namespace
    after first access so subsequent ``from decepticon.agents import X``
    calls hit the cache without re-importing.
    """
    target = _LAZY_AGENTS.get(name)
    if target is None:
        raise AttributeError(f"module 'decepticon.agents' has no attribute {name!r}")
    import importlib
    module = importlib.import_module(target)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    """Make tab-completion show every factory even though they're lazy."""
    return sorted(set(globals()) | set(_LAZY_AGENTS))


# Re-export ``SUBAGENT_SPEC`` for callers that probe the registry. The
# real SUBAGENT_SPEC objects live in each agent submodule; this hook
# preserves the previous ``from decepticon.agents import SUBAGENT_SPEC``
# shape by deferring to the first standard agent we load.
def _load_subagent_specs():
    """Load all standard-bundle subagent specs on demand.

    Returns the list of ``SubAgentSpec`` objects from the standard
    agents. Used by the langgraph server's ``subagents`` discovery.
    """
    from decepticon.agents.middleware_slots import SubAgentSpec  # noqa: F401

    specs: list = []
    # Only walk the standard subagents (decepticon + 16 + soundwave).
    standard_agents = [
        "recon", "soundwave", "analyst", "exploit", "postexploit",
        "reverser", "contract_auditor", "cloud_hunter", "ad_operator",
        "phisher", "mobile_operator", "blue_cell", "osint_operator",
        "iot_operator", "ics_operator", "forensicator",
        "supply_chain_operator", "wireless_operator",
    ]
    for role in standard_agents:
        mod_name = f"decepticon.agents.standard.{role}"
        mod = importlib.import_module(mod_name)  # noqa: F821
        spec = getattr(mod, "SUBAGENT_SPEC", None)
        if spec is not None:
            specs.append(spec)
    return specs
