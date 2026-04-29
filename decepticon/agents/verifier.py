"""Verifier Agent — Stage 3 of the vulnresearch pipeline.

Given a ``VULNERABILITY`` node from the Detector, the Verifier crafts a
minimal PoC, runs it inside the DockerSandbox, and either promotes the
vuln to a ``FINDING`` (via the Zero-False-Positive ``validate_finding``
tool) or records a reproducible failure and moves on.

The Verifier is the quality gate for the pipeline: a ``FINDING`` node
with a ``VALIDATES`` edge is the contract the Patcher and Exploiter
stages consume. False positives here poison everything downstream, so
the prompt + tool surface both lean hard into the ZFP workflow.

Tool surface:
  - ``validate_finding`` — the ZFP-enforcing PoC runner
  - ``kg_query``/``kg_neighbors``/``kg_add_node``/``kg_add_edge`` — graph
    read + bookkeeping (never emit new vuln kinds, only update existing
    ones with attempt counters)
  - ``bash`` — start services, stage PoCs, run curl sanity checks
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
from decepticon.tools.research.tools import (
    kg_add_edge,
    kg_add_node,
    kg_neighbors,
    kg_query,
    kg_stats,
    validate_finding,
)


def create_verifier_agent():
    """Initialize the Verifier Agent — sonnet, PoC-driven, ZFP gate."""
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("verifier")
    fallback_models = factory.get_fallback_models("verifier")

    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = load_prompt("verifier", shared=["bash"])

    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend,
            sources=["/skills/verifier/", "/skills/analyst/", "/skills/shared/"],
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
        validate_finding,
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_add_node,
        kg_add_edge,
        *BASH_TOOLS,
    ]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="verifier",
    ).with_config({"recursion_limit": 150})

    return agent


graph = create_verifier_agent()
