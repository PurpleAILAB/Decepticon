"""Defender Agent — autonomous defensive action execution.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely.

Middleware stack (selected for defense):
  1. DecepticonSkillsMiddleware — progressive disclosure of defender SKILL.md knowledge
  2. FilesystemMiddlewareNoExecute — ls/read/write/edit/glob/grep tools (no execute; use bash)
  3. ModelFallbackMiddleware  — primary → fallback on provider failure
  4. SummarizationMiddleware  — auto-compact when context budget exceeded
  5. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic models
  6. PatchToolCallsMiddleware  — repair dangling tool calls

Backend: DockerSandbox (single backend; /skills/ is bind-mounted into the
sandbox container — see docker-compose.yml).
"""

from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from decepticon.agents.prompts import load_prompt
from decepticon.backends import DockerDefenseBackend, DockerSandbox
from decepticon.core.config import load_config
from decepticon.llm import LLMFactory
from decepticon.middleware import (
    FilesystemMiddlewareNoExecute,
    SandboxNotificationMiddleware,
)
from decepticon.middleware.skills import DecepticonSkillsMiddleware
from decepticon.tools.bash import BASH_TOOLS
from decepticon.tools.bash.bash import set_sandbox
from decepticon.tools.defense import set_defense_backend
from decepticon.tools.defense.tools import (
    defense_execute_action,
    defense_log_action,
    defense_read_brief,
    defense_verify_status,
)
from decepticon.tools.research.tools import kg_neighbors, kg_query, kg_stats


def create_defender_agent():
    """Initialize the Defender Agent using langchain create_agent() directly.

    Context engineering decisions:
      - ModelFallbackMiddleware: primary → fallback on failure
      - No TodoListMiddleware: defense-brief.json handles task tracking
      - No SubAgentMiddleware: Decepticon orchestrator handles agent delegation

    NOTE: The defense backend uses the same sandbox container as the recon agent.
    In production, point DECEPTICON_DOCKER__SANDBOX_CONTAINER_NAME (or a dedicated
    defense container env var) at the hardened target container, not the attacker sandbox.
    """
    config = load_config()

    factory = LLMFactory()
    llm = factory.get_model("defender")
    fallback_models = factory.get_fallback_models("defender")

    # Build DockerSandbox and inject into bash tool (defensive commands run here)
    sandbox = DockerSandbox(
        container_name=config.docker.sandbox_container_name,
    )
    set_sandbox(sandbox)

    # Build DockerDefenseBackend and inject into defense tools.
    # NOTE: In production, this should target a separate defense/hardening container,
    # not the offensive sandbox. Override DECEPTICON_DOCKER__SANDBOX_CONTAINER_NAME
    # or configure a dedicated container name for the defender.
    defense_backend = DockerDefenseBackend(
        container_name=config.docker.sandbox_container_name,
    )
    set_defense_backend(defense_backend)

    system_prompt = load_prompt("defender", shared=["bash"])
    # Skills + workspace both live inside the sandbox (skills bind-mounted at /skills/).
    backend = sandbox

    # Assemble middleware stack
    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend,
            sources=["/skills/defender/", "/skills/shared/"],
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
        # Defense actions
        defense_read_brief,
        defense_execute_action,
        defense_log_action,
        defense_verify_status,
        # KG query (read-only — defender reads, does not ingest raw scan data)
        kg_query,
        kg_neighbors,
        kg_stats,
        # Execution
        *BASH_TOOLS,
    ]

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="defender",
    ).with_config({"recursion_limit": 150})

    return agent


# Module-level graph for LangGraph Platform (langgraph serve)
graph = create_defender_agent()
