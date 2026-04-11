# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Decepticon 2.0 is an AI-powered autonomous red team testing framework (Python 3.13+). LLM agents execute security reconnaissance objectives inside a Docker Kali Linux sandbox. The autonomous loop ("Ralph") reads an operations plan, spawns a fresh agent per objective, executes via bash in the sandbox, and persists findings across iterations through files on disk (not agent memory).

## Commands

```bash
uv sync --dev                          # Install with dev dependencies
pytest                                 # Run tests (asyncio auto mode)
pytest tests/unit/core/test_config.py -k test_name  # Single test
basedpyright                           # Type checking (NOT mypy)
ruff check .                           # Lint
ruff format .                          # Format
```

CLI entry point: `decepticon` starts the LangGraph dev server. The Ink CLI frontend is in `clients/cli/`.

## Architecture

**Two LLM modes** configured in `config/decepticon.yaml`:
- `apikey`: LiteLLM routes to any backend using API keys (default)
- `oauth`: Subscription-based OAuth (Claude Pro/Max, ChatGPT Plus, GitHub Copilot) with auto-refresh via `decepticon/auth/`

**Agent construction** (`agents/recon.py`, `agents/planner.py`): Both use `create_agent()` (not `create_deep_agent()`) with an explicit middleware stack: SkillsMiddleware → FilesystemMiddleware → SummarizationMiddleware → PromptCachingMiddleware → PatchToolCallsMiddleware. Recon agent has bash tool; planner agent has no tools (document generation only).

**Ralph loop** (`loop.py`): Loads `opplan.json` from disk each iteration → picks next pending objective → builds iteration prompt with RoE guard rails + previous findings → spawns fresh recon agent (clean context) → parses OBJECTIVE PASSED/BLOCKED signal → updates opplan status → appends to `findings.txt`.

**Engagement document hierarchy** stored in `/workspace/<slug>/`:
- `roe.json` — Rules of Engagement (scope constraints, checked every iteration)
- `conops.json` — threat actor profile, kill chain
- `opplan.json` — discrete objectives with acceptance criteria (drives Ralph)
- `findings/FIND-NNN.md` — per-vulnerability reports (bug bounty format)
- `findings/attack-paths/PATH-NNN.md` — kill chain traversal paths

**Knowledge Graph** (Neo4j-native attack graph):
- Neo4j is the sole persistence backend — no JSON fallback
- Each node type maps to a native Neo4j label (Host, Service, Vulnerability, etc.)
- Each relationship type maps to a native Neo4j relationship (EXPLOITS, PIVOTS_TO, etc.)
- Attack path planning uses Cypher-native APOC dijkstra, not Python-side traversal
- Schema defined in `docs/design/attack-graph-schema.md`, initialized via `scripts/init_neo4j.cypher`
- Configuration: `DECEPTICON_NEO4J_URI`, `DECEPTICON_NEO4J_USER`, `DECEPTICON_NEO4J_PASSWORD`

**Sandbox** (`backends/docker_sandbox.py`): `DockerSandbox` wraps `docker exec` with tmux session management. Named sessions allow parallel scans. PS1 polling detects command completion. Stall detection after 10s of no output change.

**Streaming** (`core/subagent_streaming.py`): `StreamingRunnable` wraps sub-agents and emits custom events (`subagent_start`, `subagent_tool_call`, `subagent_tool_result`, `subagent_message`, `subagent_end`) via LangGraph `get_stream_writer()`. The Ink CLI subscribes to these via `stream_mode="custom"`.

**CLI** (`clients/cli/`): Ink.js (React for terminal) TypeScript app. Connects to LangGraph server via `@langchain/langgraph-sdk`. Renders tool calls, bash output, and sub-agent events in real time.

## Context Engineering Conventions

This codebase is designed around controlling LLM context consumption:

1. **Observation masking** — old verbose tool outputs replaced with summaries in-place
2. **Output offloading** — bash outputs >15K chars saved to `/workspace/.scratch/` files, summary returned
3. **Output truncation** — large outputs keep 60% head + 40% tail, middle discarded
4. **Fresh agent per iteration** — no accumulated context across Ralph iterations
5. **Progressive skill disclosure** — only SKILL.md frontmatter loaded initially, full content on-demand
6. **System prompts use XML-tagged sections** (`<IDENTITY>`, `<CRITICAL_RULES>`, `<ENVIRONMENT>`, etc.)

## Code Conventions

- **Pydantic v2 everywhere**: Config uses `BaseSettings` with `env_prefix="DECEPTICON_"`. All schemas, auth types use Pydantic models. Enums use `StrEnum`.
- **Logging**: `from decepticon.core.logging import get_logger; log = get_logger("module.sub")`
- **Imports**: Public API re-exported through `__init__.py`. Internal code uses absolute imports. `from __future__ import annotations` in files with complex type hints.
- **Ruff**: line-length 100, target py313, select E/F/I/W, ignore E501.
- **Skills**: Markdown files in `skills/` with YAML frontmatter (`name`, `description`). The `description` drives progressive disclosure.

## Key Directories

- `clients/cli/` — Ink.js (React for terminal) CLI frontend (TypeScript)
- `containers/` — Dockerfiles: `langgraph.Dockerfile`, `sandbox.Dockerfile`, `cli.Dockerfile`
- `decepticon/agents/` — LangGraph agent definitions (decepticon, recon, planner, exploit, postexploit, analyst, vulnresearch pipeline, domain specialists)
- `decepticon/backends/` — Docker sandbox backend (`DockerSandbox`)
- `decepticon/auth/providers/` — OAuth implementations per LLM provider
- `decepticon/tools/` — All agent tools organized by domain:
  - `tools/bash/` — Bash execution tool (sandbox command runner)
  - `tools/research/` — KnowledgeGraph, Neo4j store, attack chain planner, CVE/fuzz/PoC
  - `tools/references/` — External reference corpus (PayloadsAllTheThings, HackerOne, killchain)
  - `tools/ad/` — Active Directory tooling (BloodHound, Kerberos, ADCS)
  - `tools/cloud/` — Cloud security (AWS IAM, K8s, Terraform)
  - `tools/contracts/` — Smart contract auditing (Solidity patterns, Slither, Foundry)
  - `tools/web/` — Web security (JWT, OAuth, GraphQL, HTTP session)
  - `tools/reversing/` — Binary analysis (strings, packer, ROP, symbols)
  - `tools/reporting/` — Report generation (HackerOne, Bugcrowd, executive)
- `skills/` — Markdown knowledge base injected via SkillsMiddleware
- `docs/design/` — Architecture design documents (attack-graph-schema.md)
- `scripts/init_neo4j.cypher` — Neo4j schema initialization
- `config/` — Runtime configs (`litellm.yaml`, `decepticon.yaml`)
- `.github/workflows/` — CI/CD (ci.yml, release.yml)
