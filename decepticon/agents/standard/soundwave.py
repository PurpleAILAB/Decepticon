"""Soundwave Agent — engagement document writer.

Generates RoE, CONOPS, and Deconfliction Plan documents that frame the
red team engagement. Does NOT generate OPPLAN — the orchestrator owns
OPPLAN directly via OPPLANMiddleware.

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

Backend: HTTPSandbox (sandbox daemon talks over HTTP; /skills/ live in the
sandbox container — see docker-compose.yml).
"""

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents.prompts import load_prompt
from decepticon.backends import build_sandbox_backend, make_agent_backend
from decepticon.llm import LLMFactory
from decepticon.middleware import EngagementContextMiddleware, FilesystemMiddleware
from decepticon.middleware.skills import SkillsMiddleware
from decepticon.plugin_loader import (
    load_plugin_callbacks,
    load_plugin_middleware,
    load_plugin_tools,
)
from decepticon.tools.interaction import ask_user_question, complete_engagement_planning


def create_soundwave_agent():
    """Initialize the Soundwave Agent using langchain create_agent() directly.

    Context engineering decisions:
      - No OPPLANMiddleware: orchestrator owns OPPLAN directly
      - No SubAgentMiddleware: soundwave is standalone
      - No bash tool: soundwave is document-generation only
      - ModelFallbackMiddleware: haiku 4.5 primary → gemini 2.5 flash fallback on failure
    """

    factory = LLMFactory()
    llm = factory.get_model("soundwave")
    fallback_models = factory.get_fallback_models("soundwave")

    # Filesystem backend — HTTPSandbox (dev / per-engagement
    # VM), HTTPSandbox when DECEPTICON_FILESYSTEM_BACKEND=http (Cloud Run
    # multi-container deploys where there's no host docker daemon). See
    # decepticon/backends/factory.py for the env contract.
    sandbox = build_sandbox_backend()

    system_prompt = load_prompt("soundwave")
    # Skills + workspace both live inside the sandbox (skills bind-mounted at /skills/).
    backend = make_agent_backend(sandbox)

    # Assemble middleware stack
    middleware = [
        EngagementContextMiddleware(),
        SkillsMiddleware(backend=backend, sources=["/skills/standard/soundwave/"]),
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

    tools = [ask_user_question, complete_engagement_planning]
    tools.extend(load_plugin_tools(role="soundwave"))
    middleware.extend(load_plugin_middleware(role="soundwave", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="soundwave",
    ).with_config(
        {
            "recursion_limit": 200,
            "callbacks": load_plugin_callbacks(role="soundwave", backend=backend),
        }
    )

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_soundwave_agent()
