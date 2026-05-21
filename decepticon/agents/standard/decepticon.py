"""Decepticon — autonomous red team coordinator agent.

Engagement-ready agent that builds the OPPLAN from existing RoE/CONOPS
documents and executes the kill chain by delegating to specialist sub-agents.
The launcher selects this assistant when the operator picks an existing
engagement; for fresh engagements it picks the standalone soundwave assistant
instead, which writes the planning documents this agent then consumes.

Uses create_agent() directly (not create_deep_agent()) to control the
middleware stack precisely.

Middleware stack (selected for orchestration):
  1. EngagementContextMiddleware — inject engagement metadata (slug, target, RoE)
  2. SkillsMiddleware — progressive disclosure of SKILL.md knowledge
  3. FilesystemMiddleware — file ops for reading/updating engagement docs
  4. SubAgentMiddleware — task() tool for delegating to sub-agents
  5. OPPLANMiddleware — OPPLAN CRUD tools (create/add/get/list/update objectives)
  6. ModelFallbackMiddleware — primary → fallback on provider failure (chain from Credentials inventory)
  7. SummarizationMiddleware — auto-compact for long orchestration sessions
  8. AnthropicPromptCachingMiddleware — cache system prompt for Anthropic models
  9. PatchToolCallsMiddleware — repair dangling tool calls

The orchestrator has tools=[] — all offensive work goes through task()
delegation to specialist sub-agents. SandboxNotificationMiddleware lives
on each sub-agent (where bash actually runs), not here.

OPPLAN provides domain-specific objective tracking:
  - CRUD tools for engagement objectives and child task trees
  - Dynamic state injection: every LLM call sees OPPLAN progress table
  - State transition validation with dependency checking

Sub-agents are passed as CompiledSubAgent, wrapping existing agent factories
(create_recon_agent, create_exploit_agent, create_postexploit_agent, and the
specialist analyst/reverser/contract_auditor/cloud_hunter/ad_operator agents)
so they run with their full middleware stack and skill sets intact. Soundwave
is intentionally NOT a sub-agent here: the launcher routes to its standalone
assistant when document generation is needed.
"""

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
from decepticon.middleware import (
    EngagementContextMiddleware,
    FilesystemMiddleware,
    OPPLANMiddleware,
    SkillsMiddleware,
)
from decepticon.plugin_loader import (
    is_bundle_enabled,
    load_plugin_callbacks,
    load_plugin_middleware,
    load_plugin_tools,
    load_subagents_for_parent,
)


def create_decepticon_agent():
    """Initialize the Decepticon Orchestrator using create_agent() directly.

    Context engineering decisions:
      - Explicit middleware stack instead of create_deep_agent() defaults
      - SubAgentMiddleware: task() tool for delegating to specialist sub-agents
      - OPPLANMiddleware: CRUD tools for objective tracking
      - ModelFallbackMiddleware: primary → fallback chain built from the user's Credentials inventory
    Returns a compiled LangGraph agent ready for invocation.
    """

    factory = LLMFactory()
    llm = factory.get_model("decepticon")
    fallback_models = factory.get_fallback_models("decepticon")

    # Filesystem backend for the orchestrator. The orchestrator has
    # tools=[], so it never touches the bash module's global _sandbox —
    # sub-agent factories set that for their own execution. HTTP transport
    # is the single supported path (see backends/factory.py).
    sandbox = build_sandbox_backend()

    system_prompt = load_prompt("decepticon")

    # CompositeBackend: HTTPSandbox serves /workspace/ over HTTP, while
    # /skills/ resolves locally from /app/skills inside the langgraph
    # container (skills are read-only knowledge, not sandbox artefacts).
    # See decepticon/backends/__init__.py:make_agent_backend.
    backend = make_agent_backend(sandbox)

    # Build sub-agents via plugin-loader discovery. Each subagent declares
    # itself as a ``SUBAGENT_SPEC`` module constant registered under the
    # ``decepticon.subagents`` entry-point group; this main agent picks
    # up every spec whose ``parent_agents`` includes ``"decepticon"``.
    # SaaS or community plugin packages can extend this roster without
    # modifying OSS — see ``decepticon/plugin_loader.py`` for the loader
    # contract and ``pyproject.toml`` for the registered specs.
    #
    # Each discovered subagent is wrapped in StreamingRunnable so its
    # tool calls, results, and AI messages stream through both Python CLI
    # (UIRenderer) and LangGraph Platform HTTP API (get_stream_writer →
    # custom events).
    #
    # Soundwave is intentionally NOT a sub-agent here: it is registered
    # at the orchestrator level (create_orchestrator) and routed to
    # whenever engagement docs are missing. Soundwave is designed
    # standalone (no SubAgentMiddleware, no bash tool — see
    # soundwave.py module docstring), so document regeneration goes
    # through the orchestrator routing, not decepticon delegation.
    # Document edits while docs already exist are handled by
    # decepticon's FilesystemMiddleware directly.
    subagents = [
        CompiledSubAgent(
            name=spec.name,
            description=spec.description,
            runnable=StreamingRunnable(spec.factory(), spec.name),
        )
        for spec in load_subagents_for_parent("decepticon")
    ]

    # Assemble middleware stack. ModelOverrideMiddleware sits ahead of
    # ModelFallbackMiddleware so the CLI ``/model`` command can swap the
    # primary at runtime while the user-configured fallback chain still
    # applies on its failure.
    from decepticon.middleware.model_override import ModelOverrideMiddleware

    middleware = [
        EngagementContextMiddleware(),
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/standard/decepticon/", "/skills/shared/", *benchmark_skill_sources()],
        ),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(backend=backend, subagents=subagents),
        OPPLANMiddleware(backend=backend),
        ModelOverrideMiddleware(),
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

    tools = list(load_plugin_tools(role="decepticon"))
    middleware.extend(load_plugin_middleware(role="decepticon", backend=backend))

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="decepticon",
    )

    # Higher recursion budget than sub-agents (100) — top-level coordinator.
    return agent.with_config(
        {
            "recursion_limit": 400,
            "callbacks": load_plugin_callbacks(role="decepticon", backend=backend),
        }
    )


# Module-level graph for LangGraph Platform.
#
# Construction is guarded by ``is_bundle_enabled("standard")`` for
# symmetry with the plugins bundle's main agent. The OSS default
# (``DECEPTICON_PLUGINS`` unset or set to ``standard``) keeps this on;
# if a user explicitly disables standard (e.g. ``DECEPTICON_PLUGINS=plugins``)
# the graph is skipped to avoid empty-subagent crashes.
if is_bundle_enabled("standard"):
    graph = create_decepticon_agent()
