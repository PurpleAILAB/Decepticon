"""Soundwave Agent — engagement document writer.

Generates RoE, CONOPS, and Deconfliction Plan documents that frame the
red team engagement. Does NOT generate OPPLAN — the orchestrator owns
OPPLAN directly via OPPLANMiddleware (Claude Code V2 Task pattern).

Named after the Decepticon intelligence officer who intercepts, processes,
and organizes strategic information for Megatron's operations.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely.

Middleware stack (selected for document writer):
  1. SkillsMiddleware — progressive disclosure of planning SKILL.md
  2. FilesystemMiddleware — ls/read/write/edit/glob/grep tools
  3. ModelFallbackMiddleware — haiku 4.5 → gemini 2.5 flash fallback on primary failure
  4. SummarizationMiddleware — auto-compact when context budget exceeded
  5. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic
  6. PatchToolCallsMiddleware — repair dangling tool calls

Backend routing (CompositeBackend):
  /skills/* → FilesystemBackend (host FS, read-only SKILL.md + references access)
  default   → DockerSandbox    (shared filesystem across agents)
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
from decepticon.middleware import EngagementContextMiddleware
from decepticon.middleware.skills import DecepticonSkillsMiddleware
from decepticon.tools.interaction import ask_user_question, complete_engagement_planning

# Resolve paths relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


def create_soundwave_agent():
    """Initialize the Soundwave Agent using langchain create_agent() directly.

    Context engineering decisions:
      - No OPPLANMiddleware: orchestrator owns OPPLAN directly
      - No SubAgentMiddleware: soundwave is standalone
      - No bash tool: soundwave is document-generation only
      - ModelFallbackMiddleware: haiku 4.5 primary → gemini 2.5 flash fallback on failure
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("soundwave")
    fallback_models = factory.get_fallback_models("soundwave")

    # DockerSandbox as shared filesystem — other agents read soundwave output here
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )

    system_prompt = load_prompt("soundwave")

    # Route /skills/ to host filesystem; everything else goes into the container
    backend = CompositeBackend(
        default=sandbox,
        routes={"/skills/": FilesystemBackend(root_dir=_REPO_ROOT / "skills", virtual_mode=True)},
    )

    # Assemble middleware stack
    middleware = [
        EngagementContextMiddleware(),
        DecepticonSkillsMiddleware(backend=backend, sources=["/skills/soundwave/"]),
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

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=[ask_user_question, complete_engagement_planning],
        middleware=middleware,
        name="soundwave",
    ).with_config({"recursion_limit": 200})

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_soundwave_agent()
