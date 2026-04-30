"""Detector Agent — Stage 2 of the vulnresearch pipeline.

Given ``CANDIDATE`` nodes emitted by the Scanner, the Detector reads the
surrounding source via :class:`FilesystemMiddleware` (Read-only) and
decides whether each candidate is a real vulnerability worth promoting.

Key design choices — all enforced by the tool surface, not just the prompt:

- **No bash tool.** The Detector is pure code-reading + graph reasoning.
  Dropping bash prevents it from shelling out to semgrep/grep/etc., which
  both wastes tokens and pollutes its context.
- **No scanner tools.** Re-scanning is the Scanner's job; the Detector
  strictly consumes scanner output.
- **No ingesters.** The ``kg_ingest_*`` surface is for machine output
  (nmap, nuclei, sarif); the Detector emits hand-crafted vuln nodes.
- **No PoC runner.** Validation belongs to the Verifier stage.

Tools exposed: the core KG CRUD + query subset of ``RESEARCH_TOOLS``, plus
``cve_lookup`` / ``cve_by_package`` for dependency correlation. Nothing else.
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
from decepticon.middleware import FilesystemMiddlewareNoExecute
from decepticon.middleware.skills import DecepticonSkillsMiddleware
from decepticon.tools.research.tools import (
    cve_by_package,
    cve_lookup,
    kg_add_edge,
    kg_add_node,
    kg_neighbors,
    kg_query,
    kg_stats,
)


def create_detector_agent():
    """Initialize the Detector Agent — sonnet-class, read-only, fresh ctx.

    Notes:
      - The Detector reads source files via FilesystemMiddleware exclusively;
        no DockerSandbox bash access.
      - Skills are sourced from ``/skills/analyst/*`` (shared with legacy
        analyst — each vuln class has its own playbook) plus a small
        detector-specific operating guide under ``/skills/detector/``.
      - ``recursion_limit=120`` — source review per candidate burns turns,
        but much less than full analyst iteration loops.
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("detector")
    fallback_models = factory.get_fallback_models("detector")

    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    # No set_sandbox() here — Detector intentionally has no bash tool.

    system_prompt = load_prompt("detector", shared=[])

    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend,
            sources=["/skills/detector/", "/skills/analyst/", "/skills/shared/"],
        ),
        FilesystemMiddlewareNoExecute(backend=backend),
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
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_add_node,
        kg_add_edge,
        cve_lookup,
        cve_by_package,
    ]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="detector",
    ).with_config({"recursion_limit": 120})

    return agent


graph = create_detector_agent()
