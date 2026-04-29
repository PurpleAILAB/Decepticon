"""AD Operator Agent — Active Directory and Windows attack lane."""

from __future__ import annotations

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents.prompts import load_prompt
from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.llm import LLMFactory
from decepticon.middleware import (
    FilesystemMiddlewareNoExecute,
    SandboxNotificationMiddleware,
)
from decepticon.middleware.skills import DecepticonSkillsMiddleware
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
    config = load_config()
    factory = LLMFactory()
    llm = factory.get_model("ad_operator")
    fallback_models = factory.get_fallback_models("ad_operator")

    sandbox = DockerSandbox(container_name=config.docker.sandbox_container_name)
    set_sandbox(sandbox)

    system_prompt = load_prompt("ad_operator", shared=["bash"])
    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(backend=backend, sources=["/skills/ad/", "/skills/shared/"]),
        FilesystemMiddlewareNoExecute(backend=backend),
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
    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="ad_operator",
    ).with_config({"recursion_limit": 250})
    return agent


graph = create_ad_operator_agent()
