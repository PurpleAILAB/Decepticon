"""Decepticon Orchestrator — autonomous red team coordinator with engagement flow routing.

Wraps the Decepticon and Soundwave agents in a StateGraph router that checks
for engagement documents (roe.json, conops.json, deconfliction.json) on every
turn. No docs → Soundwave interviews the user. Docs exist → Decepticon takes
over for OPPLAN creation and kill chain execution.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely. The orchestrator coordinates the full kill chain
by delegating to specialist sub-agents (soundwave, recon, exploit, postexploit).

Middleware stack (selected for orchestration):
  1. SafeCommandMiddleware — block session-destroying bash commands
  2. SkillsMiddleware — progressive disclosure of SKILL.md knowledge
  3. FilesystemMiddleware — file ops for reading/updating engagement docs
  4. SubAgentMiddleware — task() tool for delegating to sub-agents
  5. OPPLANMiddleware — OPPLAN CRUD tools (create/add/get/list/update objectives)
  6. ModelFallbackMiddleware — opus 4.6 → gpt-5.4 fallback on primary failure
  7. SummarizationMiddleware — auto-compact for long orchestration sessions
  8. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic
  9. PatchToolCallsMiddleware — repair dangling tool calls

OPPLAN replaces TodoListMiddleware with domain-specific objective tracking:
  - 5 CRUD tools following Claude Code's V2 Task tool patterns
  - Dynamic state injection: every LLM call sees OPPLAN progress table
  - State transition validation with dependency checking

Sub-agents are passed as CompiledSubAgent, wrapping existing agent factories
(create_recon_agent, create_exploit_agent, create_postexploit_agent, and the
specialist analyst/reverser/contract_auditor/cloud_hunter/ad_operator agents)
so they run with their full middleware stack and skill sets intact. Soundwave
is registered at the orchestrator level (see create_orchestrator), not here.
"""

import os
from pathlib import Path
from typing import Annotated, Literal, NotRequired

from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import CompiledSubAgent, SubAgentMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain.agents.middleware.types import OmitFromInput
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langgraph.graph import END, START, StateGraph

from decepticon.agents.prompts import load_prompt
from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.core.subagent_streaming import StreamingRunnable
from decepticon.llm import LLMFactory
from decepticon.middleware import OPPLANMiddleware
from decepticon.middleware.skills import DecepticonSkillsMiddleware
from decepticon.tools.bash import bash
from decepticon.tools.bash.bash import set_sandbox

# Resolve paths relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Orchestrator state & routing
# ---------------------------------------------------------------------------


class OrchestratorState(AgentState):
    """Router state for engagement flow orchestration.

    Checks for engagement docs and routes to the appropriate agent:
    - No docs → Soundwave (interview + document generation)
    - Docs exist → Decepticon (OPPLAN + kill chain execution)
    """

    has_engagement_docs: Annotated[NotRequired[bool], OmitFromInput]
    # OPPLAN fields — pass through to Decepticon subgraph
    objectives: Annotated[NotRequired[list[dict]], OmitFromInput]
    engagement_name: Annotated[NotRequired[str], OmitFromInput]
    threat_profile: Annotated[NotRequired[str], OmitFromInput]
    objective_counter: Annotated[NotRequired[int], OmitFromInput]
    workspace_path: Annotated[NotRequired[str], OmitFromInput]


def _check_engagement_docs(state: dict) -> dict:
    """Check the sandbox for existing engagement documents (roe + conops + deconfliction).

    When BENCHMARK_MODE env var is set (via .env → docker-compose), skip the
    doc check entirely and route straight to the decepticon agent.

    Routes through DockerSandbox.execute() rather than calling docker exec
    directly so all container access in this codebase shares one abstraction
    (timeouts, encoding, exit-code handling) and adapting to a different
    backend later only requires touching the backends package.
    """
    if os.getenv("BENCHMARK_MODE"):
        return {"has_engagement_docs": True}

    app_config = load_config()
    sandbox = DockerSandbox(container_name=app_config.docker.sandbox_container_name)
    try:
        result = sandbox.execute(
            "ls /workspace/*/plan/roe.json /workspace/*/plan/conops.json"
            " /workspace/*/plan/deconfliction.json 2>/dev/null | wc -l",
            timeout=5,
        )
        if result.exit_code != 0:
            return {"has_engagement_docs": False}
        count = int(result.output.strip() or "0")
    except (FileNotFoundError, OSError, ValueError):
        return {"has_engagement_docs": False}
    return {"has_engagement_docs": count >= 3}


def _route_agent(state: dict) -> Literal["soundwave", "decepticon"]:
    """Route to Soundwave (no docs) or Decepticon (docs exist)."""
    return "decepticon" if state.get("has_engagement_docs") else "soundwave"


def create_decepticon_agent():
    """Initialize the Decepticon Orchestrator using create_agent() directly.

    Context engineering decisions:
      - Explicit middleware stack instead of create_deep_agent() defaults
      - SubAgentMiddleware: task() tool for delegating to specialist sub-agents
      - OPPLANMiddleware: 5 CRUD tools for objective tracking (Claude Code V2 Task pattern)
      - ModelFallbackMiddleware: opus 4.6 primary → gpt-5.4 fallback on failure
      - CompositeBackend: /skills/* → host FS (read-only), default → Docker sandbox

    Returns a compiled LangGraph agent ready for invocation.
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("decepticon")
    fallback_models = factory.get_fallback_models("decepticon")

    # Build DockerSandbox — shared filesystem for all agents
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = load_prompt("decepticon", shared=["bash"])

    # Route /skills/ to host filesystem; everything else goes into the container
    backend = CompositeBackend(
        default=sandbox,
        routes={"/skills/": FilesystemBackend(root_dir=_REPO_ROOT / "skills", virtual_mode=True)},
    )

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
        DecepticonSkillsMiddleware(
            backend=backend, sources=["/skills/decepticon/", "/skills/shared/"]
        ),
        FilesystemMiddleware(backend=backend),
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
        tools=[bash],
        middleware=middleware,
        name="decepticon",
    )

    # Orchestrator needs a higher recursion budget than sub-agents (100).
    return agent.with_config({"recursion_limit": 200})


def create_orchestrator():
    """Build the engagement flow orchestrator graph.

    Routes each turn based on engagement document existence:
      - No engagement docs → Soundwave interviews user, generates RoE/CONOPS
      - Engagement docs exist → Decepticon builds OPPLAN, executes kill chain

    Each user message is independently routed, enabling seamless transition
    from Soundwave to Decepticon once documents are written.
    """
    from decepticon.agents.soundwave import create_soundwave_agent

    # Both subgraph nodes are added raw. LangGraph's streamSubgraphs=true
    # (set by the CLI/web in STREAM_OPTIONS) propagates each subgraph's
    # intermediate values-mode state to the parent stream automatically, so
    # AI messages and tool calls inside soundwave/decepticon surface in the
    # CLI as they happen. Wrapping the soundwave node with a custom async
    # function silently disables that propagation — the wrapper is no longer
    # a compiled-graph node, just an async callable, and the runtime stops
    # forwarding interior state events.
    #
    # The ask_user_question tool emits its own custom event via
    # get_stream_writer() inside the tool body, so the picker UX does not
    # depend on subgraph wrapping.
    soundwave = create_soundwave_agent()
    decepticon = create_decepticon_agent()

    builder = StateGraph(OrchestratorState)
    builder.add_node("check_docs", _check_engagement_docs)
    builder.add_node("soundwave", soundwave)
    builder.add_node("decepticon", decepticon)

    builder.add_edge(START, "check_docs")
    builder.add_conditional_edges("check_docs", _route_agent)
    builder.add_edge("soundwave", END)
    builder.add_edge("decepticon", END)

    return builder.compile()


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_orchestrator()
