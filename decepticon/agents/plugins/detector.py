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
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.middleware import FilesystemMiddleware
from decepticon.middleware.skills import SkillsMiddleware
from decepticon.plugin_loader import (
    SubAgentSpec,
    load_plugin_callbacks,
    load_plugin_middleware,
    load_plugin_tools,
)
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
        no sandbox bash access.
      - Skills are sourced from ``/skills/standard/analyst/*`` (shared with legacy
        analyst — each vuln class has its own playbook) plus a small
        detector-specific operating guide under ``/skills/plugins/detector/``.
      - ``recursion_limit=120`` — source review per candidate burns turns,
        but much less than full analyst iteration loops.
    """

    factory = LLMFactory()
    llm = factory.get_model("detector")
    fallback_models = factory.get_fallback_models("detector")

    sandbox = build_sandbox_backend()
    # No set_sandbox() here — Detector intentionally has no bash tool.

    system_prompt = load_prompt("detector", shared=[])

    backend = make_agent_backend(sandbox)

    middleware = [
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/plugins/detector/", "/skills/standard/analyst/", "/skills/shared/"],
        ),
        FilesystemMiddleware(backend=backend),
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

    tools.extend(load_plugin_tools(role="detector"))
    middleware.extend(load_plugin_middleware(role="detector", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="detector",
    ).with_config(
        {
            "recursion_limit": 120,
            "callbacks": load_plugin_callbacks(role="detector", backend=backend),
        }
    )

    return agent


graph = create_detector_agent()


SUBAGENT_SPEC = SubAgentSpec(
    name="detector",
    description=(
        "Stage 2 — vulnerability detector. Reads source around each "
        "CANDIDATE and promotes real bugs to VULNERABILITY + "
        "HYPOTHESIS nodes, or rejects them as false positives. "
        "Read-only (no bash)."
    ),
    factory=create_detector_agent,
    parent_agents=("vulnresearch",),
    bundle="plugins",
    priority=20,
)
