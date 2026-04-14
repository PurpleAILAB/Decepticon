"""Contract Auditor Agent — Solidity / EVM smart contract audit.

Walks a Foundry / Hardhat repo, runs the offline pattern scanner,
ingests Slither JSON, generates PoC tests via Foundry templates, and
promotes confirmed findings into the KnowledgeGraph for chain
reasoning (e.g. oracle manipulation → flash loan → drain chain).
"""

from __future__ import annotations

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
from decepticon.tools.contracts.tools import CONTRACT_TOOLS
from decepticon.tools.research.tools import (
    cve_lookup,
    kg_add_edge,
    kg_add_node,
    kg_ingest_sarif,
    kg_neighbors,
    kg_query,
    kg_stats,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def create_contract_auditor_agent():
    config = load_config()
    factory = LLMFactory()
    llm = factory.get_model("contract_auditor")
    fallback_models = factory.get_fallback_models("contract_auditor")

    sandbox = DockerSandbox(container_name=config.docker.sandbox_container_name)
    set_sandbox(sandbox)

    system_prompt = load_prompt("contract_auditor", shared=["bash"])
    backend = CompositeBackend(
        default=sandbox,
        routes={"/skills/": FilesystemBackend(root_dir=_REPO_ROOT / "skills", virtual_mode=True)},
    )

    middleware = [
        SafeCommandMiddleware(),
        DecepticonSkillsMiddleware(
            backend=backend, sources=["/skills/contracts/", "/skills/shared/"]
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
        # Contract tools
        *CONTRACT_TOOLS,
        # KG core + SARIF ingest
        kg_add_node,
        kg_add_edge,
        kg_query,
        kg_neighbors,
        kg_stats,
        kg_ingest_sarif,
        # CVE intelligence
        cve_lookup,
        # Execution
        bash,
    ]
    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware,
        name="contract_auditor",
    ).with_config({"recursion_limit": 250})
    return agent


graph = create_contract_auditor_agent()
