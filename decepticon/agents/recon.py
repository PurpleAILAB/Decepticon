"""Recon Agent — autonomous reconnaissance and intelligence gathering.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely.

Middleware stack (selected for recon):
  1. SkillsMiddleware — progressive disclosure of SKILL.md knowledge
  2. FilesystemMiddleware — ls/read/write/edit/glob/grep/execute tools
  3. ModelFallbackMiddleware — haiku 4.5 → gemini 2.5 flash fallback on primary failure
  4. SummarizationMiddleware — auto-compact when context budget exceeded
  5. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic
  6. PatchToolCallsMiddleware — repair dangling tool calls

Backend routing (CompositeBackend):
  /skills/*  → FilesystemBackend (host FS, read-only SKILL.md access)
  default    → DockerSandbox     (all file ops + bash execution in container)
"""

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents.prompts import load_prompt
from decepticon.backends import DockerSandbox
from decepticon.core.config import load_config
from decepticon.llm import LLMFactory
from decepticon.middleware import SafeCommandMiddleware
from decepticon.middleware.skills import DecepticonSkillsMiddleware
from decepticon.tools.bash import bash
from decepticon.tools.bash.bash import set_sandbox
from decepticon.tools.references.tools import killchain_lookup, oneliner_search
from decepticon.tools.research.tools import (
    kg_add_edge,
    kg_add_node,
    kg_backend_health,
    kg_ingest_dnsx,
    kg_ingest_ffuf,
    kg_ingest_httpx_jsonl,
    kg_ingest_katana,
    kg_ingest_masscan,
    kg_ingest_nmap_xml,
    kg_ingest_nuclei_jsonl,
    kg_ingest_subfinder,
    kg_ingest_testssl,
    kg_neighbors,
    kg_query,
    kg_stats,
)

# Resolve paths relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


def create_recon_agent():
    """Initialize the Recon Agent using langchain create_agent() directly.

    Context engineering decisions:
      - CompositeBackend: /skills/* → host FS (read-only), default → Docker sandbox
      - InMemoryStore: cross-thread memory for persisting findings across sessions
      - ModelFallbackMiddleware: haiku 4.5 primary → gemini 2.5 flash fallback on failure
      - No TodoListMiddleware: opplan.json handles task tracking
      - No SubAgentMiddleware: Decepticon orchestrator handles agent delegation
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("recon")
    fallback_models = factory.get_fallback_models("recon")

    # Build DockerSandbox and inject into bash tool
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    system_prompt = load_prompt("recon", shared=["bash"])

    # Route /skills/ to host filesystem; everything else goes into the container.
    # Engagement files in /workspace/ are auto-synced to host via bind mount.
    backend = CompositeBackend(
        default=sandbox,
        routes={"/skills/": FilesystemBackend(root_dir=_REPO_ROOT / "skills", virtual_mode=True)},
    )

    # Assemble middleware stack
    middleware = [
        SafeCommandMiddleware(),
        DecepticonSkillsMiddleware(backend=backend, sources=["/skills/recon/", "/skills/shared/"]),
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
        # KG core
        kg_add_node,
        kg_add_edge,
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_backend_health,
        # KG ingest (recon outputs)
        kg_ingest_nmap_xml,
        kg_ingest_nuclei_jsonl,
        kg_ingest_subfinder,
        kg_ingest_httpx_jsonl,
        kg_ingest_dnsx,
        kg_ingest_katana,
        kg_ingest_masscan,
        kg_ingest_ffuf,
        kg_ingest_testssl,
        # References
        oneliner_search,
        killchain_lookup,
        # Execution
        bash,
    ]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="recon",
    ).with_config({"recursion_limit": 200})

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_recon_agent()
