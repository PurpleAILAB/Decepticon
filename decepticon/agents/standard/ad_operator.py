"""AD Operator Agent — Active Directory and Windows attack lane."""

from __future__ import annotations

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
from decepticon.tools.ad.tools import AD_TOOLS
from decepticon.tools.bash import BASH_TOOLS
from decepticon.tools.bash.bash import set_sandbox
from decepticon.tools.references.tools import killchain_lookup
from decepticon.tools.research.tools import (
    kg_add_edge,
    kg_add_node,
    kg_ingest_asrep_hashes,
    kg_ingest_crackmapexec,
    kg_neighbors,
    kg_query,
    kg_stats,
)


def create_ad_operator_agent():
    factory = LLMFactory()
    llm = factory.get_model("ad_operator")
    fallback_models = factory.get_fallback_models("ad_operator")

    sandbox = build_sandbox_backend()
    set_sandbox(sandbox)

    system_prompt = load_prompt("ad_operator", shared=["bash"])
    backend = make_agent_backend(sandbox)

    middleware = [
        EngagementContextMiddleware(),
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/standard/ad/", "/skills/shared/", *benchmark_skill_sources()],
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
        # AD tools
        *AD_TOOLS,
        # KG core + credential ingest
        kg_add_node,
        kg_add_edge,
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_ingest_crackmapexec,
        kg_ingest_asrep_hashes,
        # References
        killchain_lookup,
        # Execution
        *BASH_TOOLS,
    ]
    tools.extend(load_plugin_tools(role="ad_operator"))
    middleware.extend(load_plugin_middleware(role="ad_operator", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="ad_operator",
    ).with_config(
        {
            "recursion_limit": 250,
            "callbacks": load_plugin_callbacks(role="ad_operator", backend=backend),
        }
    )
    return agent


graph = create_ad_operator_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="ad_operator",
    description=(
        "Active Directory / Windows attack specialist. Use after initial "
        "internal foothold: BloodHound ingestion, Kerberoast / AS-REP roast, "
        "ADCS ESC1-ESC15 scanning, DCSync candidate detection, and multi-hop "
        "AD attack path planning. Complements postexploit for Windows "
        "engagements."
    ),
    factory=create_ad_operator_agent,
    parent_agents=("decepticon",),
    bundle="standard",
    priority=70,
)
