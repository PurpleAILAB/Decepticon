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
      - Skills routed through ``/skills/scanner/`` + ``/skills/shared/``.
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("scanner")
    fallback_models = factory.get_fallback_models("scanner")

    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = load_prompt("scanner", shared=["bash"])

    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend,
            sources=["/skills/scanner/", "/skills/shared/"],
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

    # Tight tool surface: sharded scanner helpers + minimal KG read access +
    # bash for directory sizing only. NO vuln analysis tools.
    tools = [*SCANNER_TOOLS, kg_query, kg_stats, *BASH_TOOLS]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="scanner",
    ).with_config({"recursion_limit": 60})

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_scanner_agent()
