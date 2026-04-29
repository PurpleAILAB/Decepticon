"""Patcher Agent — Stage 4 of the vulnresearch pipeline.

The Patcher generates minimal diffs for validated findings and proves
the fix holds by re-running the Verifier's PoC through
:func:`decepticon.research.patch.patch_verify`. It runs on Opus with a
high recursion budget because the iteration loop (write → apply → test
→ verify → revise) can take many turns on non-trivial bugs.

Tool surface:
  - ``patch_propose`` / ``patch_verify`` — proposal + ZFP verification
  - ``kg_query`` / ``kg_neighbors`` — read verified findings
  - Filesystem Edit / Read via ``FilesystemMiddleware`` — apply diffs
  - ``bash`` — run the repo's test suite and stage test commands
"""

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
from decepticon.tools.research.patch import patch_propose, patch_verify
from decepticon.tools.research.tools import (
    kg_neighbors,
    kg_query,
    kg_stats,
)


def create_patcher_agent():
    """Initialize the Patcher Agent — opus, iterative fix-verify loops."""
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("patcher")
    fallback_models = factory.get_fallback_models("patcher")

    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = load_prompt("patcher", shared=["bash"])

    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend,
            sources=["/skills/patcher/", "/skills/shared/"],
        ),
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
        patch_propose,
        patch_verify,
        kg_query,
        kg_neighbors,
        kg_stats,
        *BASH_TOOLS,
    ]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="patcher",
    ).with_config({"recursion_limit": 200})

    return agent


graph = create_patcher_agent()
