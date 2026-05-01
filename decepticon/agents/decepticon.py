"""Decepticon — autonomous red team coordinator agent.

Engagement-ready agent that builds the OPPLAN from existing RoE/CONOPS
documents and executes the kill chain by delegating to specialist sub-agents.
The launcher selects this assistant when the operator picks an existing
engagement; for fresh engagements it picks the standalone soundwave assistant
instead, which writes the planning documents this agent then consumes.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely.

Middleware stack (selected for orchestration):
  1. EngagementContextMiddleware — inject engagement metadata (slug, target, RoE)
  2. DecepticonSkillsMiddleware — progressive disclosure of SKILL.md knowledge
  3. FilesystemMiddlewareNoExecute — file ops for reading/updating engagement docs
  4. SubAgentMiddleware — task() tool for delegating to sub-agents
  5. OPPLANMiddleware — OPPLAN CRUD tools (create/add/get/list/update objectives)
  6. ModelFallbackMiddleware — primary → fallback on provider failure (chain from Credentials inventory)
  7. SummarizationMiddleware — auto-compact for long orchestration sessions
  8. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic models
  9. PatchToolCallsMiddleware — repair dangling tool calls

The orchestrator has tools=[] — all offensive work goes through task()
delegation to specialist sub-agents. SandboxNotificationMiddleware lives
on each sub-agent (where bash actually runs), not here.

OPPLAN replaces TodoListMiddleware with domain-specific objective tracking:
  - 5 CRUD tools following Claude Code's V2 Task tool patterns
  - Dynamic state injection: every LLM call sees OPPLAN progress table
  - State transition validation with dependency checking

Sub-agents are passed as CompiledSubAgent, wrapping existing agent factories
(create_recon_agent, create_exploit_agent, create_postexploit_agent, and the
specialist analyst/reverser/contract_auditor/cloud_hunter/ad_operator agents)
so they run with their full middleware stack and skill sets intact. Soundwave
is intentionally NOT a sub-agent here: the launcher routes to its standalone
assistant when document generation is needed.
"""

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import CompiledSubAgent, SubAgentMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents.prompts import load_prompt
from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.core.subagent_streaming import StreamingRunnable
from decepticon.llm import LLMFactory
from decepticon.middleware import (
    DecepticonSkillsMiddleware,
    EngagementContextMiddleware,
    FilesystemMiddlewareNoExecute,
    OPPLANMiddleware,
)


def create_decepticon_agent():
    """Initialize the Decepticon Orchestrator using create_agent() directly.

    Context engineering decisions:
      - Explicit middleware stack instead of create_deep_agent() defaults
      - SubAgentMiddleware: task() tool for delegating to specialist sub-agents
      - OPPLANMiddleware: 5 CRUD tools for objective tracking (Claude Code V2 Task pattern)
      - ModelFallbackMiddleware: primary → fallback chain built from the user's Credentials inventory
    Returns a compiled LangGraph agent ready for invocation.
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("decepticon")
    fallback_models = factory.get_fallback_models("decepticon")

    # DockerSandbox here only backs FilesystemMiddlewareNoExecute (read/write
    # engagement docs). The orchestrator has tools=[], so the bash module's
    # global _sandbox is set by sub-agent factories when they execute.
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )

    system_prompt = load_prompt("decepticon")

    # Single backend: DockerSandbox provides /workspace/ AND /skills/ (skills
    # are bind-mounted into the sandbox container at /skills/, see
    # docker-compose.yml). All file I/O goes through the sandbox so the
    # langgraph process never reads from the host filesystem.
    backend = sandbox

    # Build sub-agents from existing agent factories
    from decepticon.agents.ad_operator import create_ad_operator_agent
    from decepticon.agents.analyst import create_analyst_agent
    from decepticon.agents.cloud_hunter import create_cloud_hunter_agent
    from decepticon.agents.contract_auditor import create_contract_auditor_agent
    from decepticon.agents.exploit import create_exploit_agent
    from decepticon.agents.postexploit import create_postexploit_agent
    from decepticon.agents.recon import create_recon_agent
    from decepticon.agents.reverser import create_reverser_agent

    # Wrap each sub-agent with StreamingRunnable so their tool calls, results,
    # and AI messages stream through both Python CLI (UIRenderer) and
    # LangGraph Platform HTTP API (get_stream_writer → custom events).
    #
    # Soundwave is intentionally NOT a sub-agent here: it is registered at the
    # orchestrator level (create_orchestrator) and routed to whenever
    # engagement docs are missing. Soundwave is designed standalone (no
    # SubAgentMiddleware, no bash tool — see soundwave.py module docstring),
    # so document regeneration goes through the orchestrator routing, not
    # decepticon delegation. Document edits while docs already exist are
    # handled by decepticon's FilesystemMiddleware directly.
    subagents = [
        CompiledSubAgent(
            name="recon",
            description=(
                "Reconnaissance agent. Passive/active recon, OSINT, web/cloud recon. "
                "Use for: subdomain enumeration, port scanning, service detection, "
                "vulnerability scanning, OSINT gathering. "
                "Saves results to /workspace/recon/"
            ),
            runnable=StreamingRunnable(create_recon_agent(), "recon"),
        ),
        CompiledSubAgent(
            name="exploit",
            description=(
                "Exploitation agent. Initial access via web/AD attacks. "
                "Use for: SQLi, SSTI, Kerberoasting, ADCS abuse, credential attacks. "
                "Use after recon identifies attack surface. "
                "Saves results to /workspace/exploit/"
            ),
            runnable=StreamingRunnable(create_exploit_agent(), "exploit"),
        ),
        CompiledSubAgent(
            name="analyst",
            description=(
                "Vulnerability research agent — the high-value discovery lane. "
                "Use for: source code review, static analysis (semgrep/bandit/gitleaks), "
                "dependency CVE sweeps, silent-patch diff hunting, fuzzing, taint "
                "analysis for SSRF/SQLi/IDOR/deserialization/prototype-pollution/"
                "command-injection/prompt-injection, and multi-hop exploit chain "
                "construction. Writes all observations into the KnowledgeGraph "
                "backend (default /workspace/kg.json, optional Neo4j) so "
                "findings survive across iterations."
            ),
            runnable=StreamingRunnable(create_analyst_agent(), "analyst"),
        ),
        CompiledSubAgent(
            name="reverser",
            description=(
                "Binary reversing specialist. Use for ELF/PE/Mach-O/firmware triage, "
                "packer detection, classified string extraction, symbol risk reports, "
                "ROP gadget inventories, and Ghidra/radare2 recon script generation. "
                "Ideal for thick clients, IoT firmware, game cheats, malware triage, "
                "and exploit dev hand-offs."
            ),
            runnable=StreamingRunnable(create_reverser_agent(), "reverser"),
        ),
        CompiledSubAgent(
            name="contract_auditor",
            description=(
                "Solidity / EVM smart contract audit specialist. Use for DeFi / "
                "smart-contract engagements: reentrancy, oracle manipulation, flash "
                "loan abuse, access control gaps, upgradeable proxies, signature "
                "replay. Runs Slither ingestion, solidity pattern scanner, and "
                "Foundry PoC test harness generation."
            ),
            runnable=StreamingRunnable(create_contract_auditor_agent(), "contract_auditor"),
        ),
        CompiledSubAgent(
            name="cloud_hunter",
            description=(
                "AWS / Azure / GCP / Kubernetes exploitation specialist. Use for "
                "IAM policy privesc, S3 bucket takeover, Kubernetes RBAC / hostPath "
                "escapes, Terraform state secret extraction, and cloud metadata "
                "pivoting after an SSRF is confirmed by recon or analyst."
            ),
            runnable=StreamingRunnable(create_cloud_hunter_agent(), "cloud_hunter"),
        ),
        CompiledSubAgent(
            name="ad_operator",
            description=(
                "Active Directory / Windows attack specialist. Use after initial "
                "internal foothold: BloodHound ingestion, Kerberoast / AS-REP roast, "
                "ADCS ESC1-ESC15 scanning, DCSync candidate detection, and multi-hop "
                "AD attack path planning. Complements postexploit for Windows "
                "engagements."
            ),
            runnable=StreamingRunnable(create_ad_operator_agent(), "ad_operator"),
        ),
        CompiledSubAgent(
            name="postexploit",
            description=(
                "Post-exploitation agent. Credential access, privilege escalation, "
                "lateral movement, C2 management. "
                "Use after initial foothold is established. "
                "Saves results to /workspace/post-exploit/"
            ),
            runnable=StreamingRunnable(create_postexploit_agent(), "postexploit"),
        ),
    ]

    # Assemble middleware stack
    middleware = [
        EngagementContextMiddleware(),
        DecepticonSkillsMiddleware(
            backend=backend, sources=["/skills/decepticon/", "/skills/shared/"]
        ),
        FilesystemMiddlewareNoExecute(backend=backend),
        SubAgentMiddleware(backend=backend, subagents=subagents),
        OPPLANMiddleware(),
    ]
    if fallback_models:
        middleware.append(ModelFallbackMiddleware(*fallback_models))
    middleware.extend(
        [
            create_summarization_middleware(llm, backend),
            AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
            PatchToolCallsMiddleware(),
        ]
    )

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=[],
        middleware=middleware,
        name="decepticon",
    )

    # Higher recursion budget than sub-agents (100) — top-level coordinator.
    return agent.with_config({"recursion_limit": 400})


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_decepticon_agent()
