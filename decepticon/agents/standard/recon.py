"""Recon Agent — autonomous reconnaissance and intelligence gathering.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely.

Middleware stack (selected for recon):
  1. SkillsMiddleware — progressive disclosure of SKILL.md knowledge
  2. FilesystemMiddleware — ls/read/write/edit/glob/grep tools (no execute; use bash)
  3. ModelFallbackMiddleware — haiku 4.5 → gemini 2.5 flash fallback on primary failure
  4. SummarizationMiddleware — auto-compact when context budget exceeded
  5. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic
  6. PatchToolCallsMiddleware — repair dangling tool calls

Backend: HTTPSandbox (sandbox daemon talks over HTTP; /skills/ live in the
sandbox container — see docker-compose.yml).
"""

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents._benchmark_mode import benchmark_skill_sources
from decepticon.agents.prompts import load_prompt
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.middleware import (
    EngagementContextMiddleware,
    FilesystemMiddleware,
    SandboxNotificationMiddleware,
)
from decepticon.middleware.skills import SkillsMiddleware
from decepticon.plugin_loader import (
    SubAgentSpec,
    load_plugin_callbacks,
    load_plugin_middleware,
    load_plugin_tools,
)
from decepticon.tools.bash import BASH_TOOLS
from decepticon.tools.bash.bash import set_sandbox
from decepticon.tools.references.tools import killchain_lookup, oneliner_search
from decepticon.tools.research.tools import (
    kg_add_edge,
    kg_add_node,
    kg_backend_health,
    kg_ingest_dnsx,
    kg_ingest_ffuf,
    kg_ingest_httpx_jsonl,
    kg_ingest_katana,
    kg_ingest_masscan,
    kg_ingest_nmap_xml,
    kg_ingest_nuclei_jsonl,
    kg_ingest_subfinder,
    kg_ingest_testssl,
    kg_neighbors,
    kg_query,
    kg_stats,
)


def create_recon_agent():
    """Initialize the Recon Agent using langchain create_agent() directly.

    Context engineering decisions:      - InMemoryStore: cross-thread memory for persisting findings across sessions
      - ModelFallbackMiddleware: haiku 4.5 primary → gemini 2.5 flash fallback on failure
      - OPPLAN is owned by the orchestrator; this specialist writes evidence only
      - No SubAgentMiddleware: Decepticon orchestrator handles agent delegation
    """

    factory = LLMFactory()
    llm = factory.get_model("recon")
    fallback_models = factory.get_fallback_models("recon")

    # Build HTTPSandbox and inject into bash tool
    sandbox = build_sandbox_backend()
    set_sandbox(sandbox)

    system_prompt = load_prompt("recon", shared=["bash"])
    # Skills + workspace both live inside the sandbox (skills bind-mounted at /skills/).
    backend = make_agent_backend(sandbox)

    # Assemble middleware stack
    middleware = [
        EngagementContextMiddleware(),
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/standard/recon/", "/skills/shared/", *benchmark_skill_sources()],
        ),
        FilesystemMiddleware(backend=backend),
        SandboxNotificationMiddleware(sandbox=sandbox),
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

    tools = [
        # KG core
        kg_add_node,
        kg_add_edge,
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_backend_health,
        # KG ingest (recon outputs)
        kg_ingest_nmap_xml,
        kg_ingest_nuclei_jsonl,
        kg_ingest_subfinder,
        kg_ingest_httpx_jsonl,
        kg_ingest_dnsx,
        kg_ingest_katana,
        kg_ingest_masscan,
        kg_ingest_ffuf,
        kg_ingest_testssl,
        # References
        oneliner_search,
        killchain_lookup,
        # Execution
        *BASH_TOOLS,
    ]

    tools.extend(load_plugin_tools(role="recon"))
    middleware.extend(load_plugin_middleware(role="recon", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="recon",
    ).with_config(
        {"recursion_limit": 1000, "callbacks": load_plugin_callbacks(role="recon", backend=backend)}
    )

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_recon_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="recon",
    description=(
        "Reconnaissance agent. Passive/active recon, OSINT, web/cloud recon. "
        "Use for: subdomain enumeration, port scanning, service detection, "
        "vulnerability scanning, OSINT gathering. "
        "Saves results under the active engagement workspace's recon/ directory."
    ),
    factory=create_recon_agent,
    parent_agents=("decepticon",),
    bundle="standard",
    priority=10,
)
