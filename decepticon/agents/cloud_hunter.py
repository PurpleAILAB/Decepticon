"""Cloud Hunter Agent — AWS/Azure/GCP/k8s exploitation lane."""

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
from decepticon.tools.bash import BASH_TOOLS
from decepticon.tools.bash.bash import set_sandbox
from decepticon.tools.cloud.tools import CLOUD_TOOLS
from decepticon.tools.research.tools import (
    cve_lookup,
    kg_add_edge,
    kg_add_node,
    kg_neighbors,
    kg_query,
    kg_stats,
)


def create_cloud_hunter_agent():
    config = load_config()
    factory = LLMFactory()
    llm = factory.get_model("cloud_hunter")
    fallback_models = factory.get_fallback_models("cloud_hunter")

    sandbox = DockerSandbox(container_name=config.docker.sandbox_container_name)
    set_sandbox(sandbox)

    system_prompt = load_prompt("cloud_hunter", shared=["bash"])
    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(backend=backend, sources=["/skills/cloud/", "/skills/shared/"]),
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
        # Cloud tools
        *CLOUD_TOOLS,
        # KG core
        kg_add_node,
        kg_add_edge,
        kg_query,
        kg_neighbors,
        kg_stats,
        # CVE intelligence
        cve_lookup,
        # Execution
        *BASH_TOOLS,
    ]
    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="cloud_hunter",
    ).with_config({"recursion_limit": 250})
    return agent


graph = create_cloud_hunter_agent()
