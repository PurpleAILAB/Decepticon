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

from decepticon.agents.prompts import load_prompt
from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.core.subagent_streaming import StreamingRunnable
from decepticon.llm import LLMFactory
from decepticon.middleware import FilesystemMiddlewareNoExecute, OPPLANMiddleware
from decepticon.middleware.skills import DecepticonSkillsMiddleware
from decepticon.tools.research.tools import kg_query, kg_stats


def create_vulnresearch_agent():
    """Initialize the Vulnresearch Orchestrator.

    Tool surface is intentionally tiny: ``kg_query`` + ``kg_stats`` for
    graph inspection, plus the OPPLAN CRUD tools (injected by
    :class:`OPPLANMiddleware`) and the ``task()`` dispatcher (injected
    by :class:`SubAgentMiddleware`). Everything else is delegated.
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("vulnresearch")
    fallback_models = factory.get_fallback_models("vulnresearch")

    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    # NOTE: do NOT call set_sandbox() here — the orchestrator must not
    # run bash. Each sub-agent that does need bash calls set_sandbox()
    # from its own factory.

    system_prompt = load_prompt("vulnresearch", shared=[])

    backend = sandbox

    # Import factories lazily so a broken sub-agent definition surfaces
    # at instantiation time, not at module-import time (matching
    # decepticon.py's pattern).
    from decepticon.agents.detector import create_detector_agent
    from decepticon.agents.exploiter import create_exploiter_agent
    from decepticon.agents.patcher import create_patcher_agent
    from decepticon.agents.scanner import create_scanner_agent
    from decepticon.agents.verifier import create_verifier_agent

    subagents = [
        CompiledSubAgent(
            name="scanner",
            description=(
                "Stage 1 — broad-spectrum scanner. Walks very large codebases "
                "in parallel shards and emits CANDIDATE nodes with heuristic "
                "suspicion scores. Use first on any new target. Cheap, fast, "
                "no vulnerability reasoning."
            ),
            runnable=StreamingRunnable(create_scanner_agent(), "scanner"),
        ),
        CompiledSubAgent(
            name="detector",
            description=(
                "Stage 2 — vulnerability detector. Reads source around each "
                "CANDIDATE and promotes real bugs to VULNERABILITY + "
                "HYPOTHESIS nodes, or rejects them as false positives. "
                "Read-only (no bash)."
            ),
            runnable=StreamingRunnable(create_detector_agent(), "detector"),
        ),
        CompiledSubAgent(
            name="verifier",
            description=(
                "Stage 3 — triage and verification. Builds minimal PoCs for "
                "VULNERABILITY nodes, runs them inside the DockerSandbox "
                "with Zero-False-Positive controls, and promotes confirmed "
                "bugs to FINDING nodes with CVSS vectors."
            ),
            runnable=StreamingRunnable(create_verifier_agent(), "verifier"),
        ),
        CompiledSubAgent(
            name="patcher",
            description=(
                "Stage 4 — patch generation. Writes minimal diffs for "
                "validated findings, applies them, and proves the fix via "
                "patch_verify (re-runs the PoC, expects failure). Opus "
                "tier, iterative."
            ),
            runnable=StreamingRunnable(create_patcher_agent(), "patcher"),
        ),
        CompiledSubAgent(
            name="exploiter",
            description=(
                "Stage 5 (optional) — exploit construction. Chains "
                "validated primitives into weaponized attack paths that "
                "reach a CROWN_JEWEL node. Uses plan_attack_chains and "
                "can hand off to the reverser for binary work."
            ),
            runnable=StreamingRunnable(create_exploiter_agent(), "exploiter"),
        ),
    ]

    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend, sources=["/skills/vulnresearch/", "/skills/shared/"]
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

    # Tiny tool surface: only read the graph. All work is delegated.
    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=[kg_query, kg_stats],
        middleware=middleware,
        name="vulnresearch",
    )

    # Higher ceiling than specialists because the orchestrator needs
    # many delegation rounds across five stages.
    return agent.with_config({"recursion_limit": 250})


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_vulnresearch_agent()
