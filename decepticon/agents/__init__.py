# Standard bundle — decepticon main agent + 8 official subagents + soundwave.
# Plugins bundle — vulnresearch main agent + its 5 subagents (community-plugin
# shape demonstrated from inside OSS). See decepticon/agents/plugins/__init__.py.
from decepticon.agents.plugins.detector import create_detector_agent
from decepticon.agents.plugins.exploiter import create_exploiter_agent
from decepticon.agents.plugins.patcher import create_patcher_agent
from decepticon.agents.plugins.scanner import create_scanner_agent
from decepticon.agents.plugins.verifier import create_verifier_agent
from decepticon.agents.plugins.vulnresearch import create_vulnresearch_agent
from decepticon.agents.standard.ad_operator import create_ad_operator_agent
from decepticon.agents.standard.analyst import create_analyst_agent
from decepticon.agents.standard.cloud_hunter import create_cloud_hunter_agent
from decepticon.agents.standard.contract_auditor import create_contract_auditor_agent
from decepticon.agents.standard.decepticon import create_decepticon_agent
from decepticon.agents.standard.exploit import create_exploit_agent
from decepticon.agents.standard.postexploit import create_postexploit_agent
from decepticon.agents.standard.recon import create_recon_agent
from decepticon.agents.standard.reverser import create_reverser_agent
from decepticon.agents.standard.soundwave import create_soundwave_agent

__all__ = [
    "create_recon_agent",
    "create_soundwave_agent",
    "create_analyst_agent",
    "create_exploit_agent",
    "create_postexploit_agent",
    "create_decepticon_agent",
    "create_reverser_agent",
    "create_contract_auditor_agent",
    "create_cloud_hunter_agent",
    "create_ad_operator_agent",
    # Vulnresearch pipeline (five-stage modular)
    "create_scanner_agent",
    "create_detector_agent",
    "create_verifier_agent",
    "create_patcher_agent",
    "create_exploiter_agent",
    "create_vulnresearch_agent",
]
