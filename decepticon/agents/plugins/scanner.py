"""Scanner Agent — Stage 1 of the vulnresearch pipeline.

Broad-spectrum triage over large codebases (10^4 – 10^6 files). Runs on
the cheapest model tier available (Haiku) with a tight tool surface
focused on the sharded scanner helpers in
:mod:`decepticon.research.scanner_tools`.

The scanner deliberately has **no vulnerability-reasoning tools** — no
CVE lookup, no chain planner, no PoC validator. Its only job is to
produce ``CANDIDATE`` nodes for the Detector (Stage 2) to promote or
reject.

See ``decepticon/agents/prompts/scanner.md`` for the operating loop.
"""

from __future__ import annotations

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

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
from decepticon.tools.research.scanner_tools import SCANNER_TOOLS
from decepticon.tools.research.tools import kg_query, kg_stats


def create_scanner_agent():
    """Initialize the Scanner Agent — cheap, sharded, candidate-only.

    Context engineering decisions:
      - Haiku-tier primary (see ``LLMModelMapping.scanner``) so 10^5-file
        sweeps cost pennies.
      - ``recursion_limit=60`` — scanner work is shallow; if it needs more
        iterations something is wrong (probably reading whole files).
      - Tools: sharded scanner helpers + ``kg_query`` + ``kg_stats``, plus
        ``bash`` for directory sizing (``du``, ``wc -l``, ``ls``). No other
        research tools.
      - Skills routed through ``/skills/plugins/scanner/`` + ``/skills/shared/``.
    """

    factory = LLMFactory()
    llm = factory.get_model("scanner")
    fallback_models = factory.get_fallback_models("scanner")

    sandbox = build_sandbox_backend()
    set_sandbox(sandbox)

    system_prompt = load_prompt("scanner", shared=["bash"])

    backend = make_agent_backend(sandbox)

    middleware = [
        EngagementContextMiddleware(),
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/plugins/scanner/", "/skills/shared/"],
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

    # Tight tool surface: sharded scanner helpers + minimal KG read access +
    # bash for directory sizing only. NO vuln analysis tools.
    tools = [*SCANNER_TOOLS, kg_query, kg_stats, *BASH_TOOLS]

    tools.extend(load_plugin_tools(role="scanner"))
    middleware.extend(load_plugin_middleware(role="scanner", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="scanner",
    ).with_config(
        {"recursion_limit": 60, "callbacks": load_plugin_callbacks(role="scanner", backend=backend)}
    )

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_scanner_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="scanner",
    description=(
        "Stage 1 — broad-spectrum scanner. Walks very large codebases "
        "in parallel shards and emits CANDIDATE nodes with heuristic "
        "suspicion scores. Use first on any new target. Cheap, fast, "
        "no vulnerability reasoning."
    ),
    factory=create_scanner_agent,
    parent_agents=("vulnresearch",),
    bundle="plugins",
    priority=10,
)
