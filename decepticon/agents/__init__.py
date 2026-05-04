from decepticon.agents.ad_operator import create_ad_operator_agent
from decepticon.agents.analyst import create_analyst_agent
from decepticon.agents.cloud_hunter import create_cloud_hunter_agent
from decepticon.agents.contract_auditor import create_contract_auditor_agent
from decepticon.agents.decepticon import create_decepticon_agent
from decepticon.agents.detector import create_detector_agent
from decepticon.agents.exploit import create_exploit_agent
from decepticon.agents.exploiter import create_exploiter_agent
from decepticon.agents.patcher import create_patcher_agent
from decepticon.agents.postexploit import create_postexploit_agent
from decepticon.agents.recon import create_recon_agent
from decepticon.agents.reverser import create_reverser_agent
from decepticon.agents.scanner import create_scanner_agent
from decepticon.agents.soundwave import create_soundwave_agent
from decepticon.agents.verifier import create_verifier_agent
from decepticon.agents.vulnresearch import create_vulnresearch_agent

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
