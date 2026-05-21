"""Vulnresearch Orchestrator — five-stage modular vulnerability pipeline.

Mirrors :mod:`decepticon.agents.decepticon` (the red-team orchestrator)
but swaps the sub-agent roster for the five vulnresearch specialists:
scanner → detector → verifier → patcher → exploiter. State passes
between stages exclusively through the KnowledgeGraph backend (default
``/workspace/kg.json``; optional Neo4j), so every sub-agent runs with
fresh context and only reads the slice of graph state that matters for
its work item.

Design notes:
  - Uses ``create_agent()`` directly with an explicit middleware stack
    so the OPPLAN tracker, SubAgent dispatcher, and skills loader are
    all composed deterministically.
  - Sub-agents are wrapped in :class:`StreamingRunnable` so their tool
    calls and messages stream through both the Python CLI and the
    LangGraph Platform HTTP API.
  - The orchestrator itself has only ``kg_query``/``kg_stats`` as tools
    (plus the SubAgent ``task()`` and OPPLAN CRUD). It MUST NOT touch
    bash, source files, or PoCs directly.
"""

from __future__ import annotations

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import CompiledSubAgent, SubAgentMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents._benchmark_mode import benchmark_skill_sources
from decepticon.agents.prompts import load_prompt
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.core.subagent_streaming import StreamingRunnable
from decepticon.llm import LLMFactory
from decepticon.middleware import FilesystemMiddleware, OPPLANMiddleware
from decepticon.middleware.skills import SkillsMiddleware
from decepticon.plugin_loader import (
    is_bundle_enabled,
    load_plugin_callbacks,
    load_plugin_middleware,
    load_plugin_tools,
    load_subagents_for_parent,
)
from decepticon.tools.research.tools import kg_query, kg_stats


def create_vulnresearch_agent():
    """Initialize the Vulnresearch Orchestrator.

    Tool surface is intentionally tiny: ``kg_query`` + ``kg_stats`` for
    graph inspection, plus the OPPLAN CRUD tools (injected by
    :class:`OPPLANMiddleware`) and the ``task()`` dispatcher (injected
    by :class:`SubAgentMiddleware`). Everything else is delegated.
    """

    factory = LLMFactory()
    llm = factory.get_model("vulnresearch")
    fallback_models = factory.get_fallback_models("vulnresearch")

    sandbox = build_sandbox_backend()
    # NOTE: do NOT call set_sandbox() here — the orchestrator must not
    # run bash. Each sub-agent that does need bash calls set_sandbox()
    # from its own factory.

    system_prompt = load_prompt("vulnresearch", shared=[])

    backend = make_agent_backend(sandbox)

    # Build sub-agents via plugin-loader discovery. Each subagent
    # declares itself as a ``SUBAGENT_SPEC`` module constant registered
    # under the ``decepticon.subagents`` entry-point group; this main
    # agent picks up every spec whose ``parent_agents`` includes
    # ``"vulnresearch"``. Community or SaaS plugin packages can extend
    # this roster without modifying OSS — see
    # ``decepticon/plugin_loader.py`` for the loader contract.
    subagents = [
        CompiledSubAgent(
            name=spec.name,
            description=spec.description,
            runnable=StreamingRunnable(spec.factory(), spec.name),
        )
        for spec in load_subagents_for_parent("vulnresearch")
    ]

    middleware = [
        SkillsMiddleware(
            backend=backend,
            sources=[
                "/skills/plugins/vulnresearch/",
                "/skills/shared/",
                *benchmark_skill_sources(),
            ],
        ),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(backend=backend, subagents=subagents),
        OPPLANMiddleware(backend=backend),
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

    # Tiny tool surface: only read the graph. All work is delegated.
    tools = [kg_query, kg_stats]
    tools.extend(load_plugin_tools(role="vulnresearch"))
    middleware.extend(load_plugin_middleware(role="vulnresearch", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="vulnresearch",
    )

    # Higher ceiling than specialists because the orchestrator needs
    # many delegation rounds across five stages.
    return agent.with_config(
        {
            "recursion_limit": 250,
            "callbacks": load_plugin_callbacks(role="vulnresearch", backend=backend),
        }
    )


# Module-level graph for LangGraph Platform.
#
# Construction is guarded by ``is_bundle_enabled("plugins")``: when the
# bundle is disabled (the OSS default) the subagent roster is empty,
# which would otherwise cause ``SubAgentMiddleware`` to raise at
# module-import time. Skipping construction keeps ``import
# decepticon.agents.plugins.vulnresearch`` side-effect-free for default
# installs; opt-in via ``DECEPTICON_PLUGINS=standard,plugins`` (or the
# equivalent config-file entry) flips this on.
if is_bundle_enabled("plugins"):
    graph = create_vulnresearch_agent()
