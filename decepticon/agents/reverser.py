"""Reverser Agent — binary analysis, firmware triage, exploit dev.

Specialises in taking an opaque binary (ELF, PE, Mach-O, firmware
image) and turning it into structured findings: dangerous imports,
embedded secrets, packer signatures, ROP gadget inventories, and
recon scripts for Ghidra / radare2 follow-up.

Tool surface (first-class research tools + bash):
    bin_identify, bin_strings, bin_packer, bin_rop,
    bin_symbols_report, bin_ghidra_script, bin_r2_script,
    + everything from the research.tools package.
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
from decepticon.tools.research.tools import (
    kg_add_edge,
    kg_add_node,
    kg_neighbors,
    kg_query,
    kg_stats,
    kg_triage_binary,
)
from decepticon.tools.reversing.tools import REVERSING_TOOLS


def create_reverser_agent():
    config = load_config()
    factory = LLMFactory()
    llm = factory.get_model("reverser")
    fallback_models = factory.get_fallback_models("reverser")

    sandbox = DockerSandbox(container_name=config.docker.sandbox_container_name)
    set_sandbox(sandbox)

    system_prompt = load_prompt("reverser", shared=["bash"])
    backend = sandbox

    middleware = [
        DecepticonSkillsMiddleware(
            backend=backend, sources=["/skills/reverser/", "/skills/shared/"]
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
        # Reversing tools
        *REVERSING_TOOLS,
        # KG core + binary triage
        kg_add_node,
        kg_add_edge,
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_triage_binary,
        # Execution
        *BASH_TOOLS,
    ]
    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="reverser",
    ).with_config({"recursion_limit": 250})
    return agent


graph = create_reverser_agent()
