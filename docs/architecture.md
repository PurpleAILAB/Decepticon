# Architecture

## Overview

Decepticon runs on two Docker networks. Management infrastructure (LLM proxy, databases, agent API) and operational infrastructure (sandbox, C2, targets) are separated so that no offensive tool inside the sandbox can reach the LLM gateway, the API surface, or your credentials over the network. The agent drives the sandbox via the Docker socket, never via TCP.

```
┌──────────────────────────────────────────────────────────────┐
│                     User Interfaces                          │
│          Terminal CLI (Ink)        Web Dashboard (Next.js)   │
└─────────────────────────┬────────────────────────────────────┘
                          │ SSE / LangGraph SDK
┌─────────────────────────▼────────────────────────────────────┐
│                  LangGraph Platform (port 2024)               │
│              Agent Orchestration & Event Streaming            │
└──────────┬───────────────────────────────────────────────────┘
           │                              │ Docker socket only
┌──────────▼──────────┐                   │
│   decepticon-net    │       ┌───────────▼──────────────────┐
│                     │       │       sandbox-net            │
│  LiteLLM    :4000   │       │                              │
│  PostgreSQL :5432   │       │  Sandbox (Kali Linux)        │
│  LangGraph  :2024   │       │  C2 Server (Sliver)          │
│  Web        :3000   │       │  Victim targets              │
│                     │       │                              │
│  Neo4j ◀────────────┼───────┼──▶ Neo4j  :7687/:7474        │
│  (dual-homed bolt:// for agent + sandbox writes)            │
└─────────────────────┘       └──────────────────────────────┘
       Management                       Operations
   (LLM, persistence, UI)        (exploitation, C2, targets)
```

**Network boundaries.** The sandbox cannot reach LiteLLM, PostgreSQL, the LangGraph API, or the web dashboard — none of the management services are routable from `sandbox-net`. The agent inside LangGraph cannot reach attack tooling over a TCP socket; the only channel into the sandbox is `docker exec` via the Docker socket bind-mount.

**Neo4j is the one shared service** — it sits on both networks because the sandbox writes findings into it (`bolt://neo4j:7687` from inside Kali) and the agent reads them back (`bolt://neo4j:7687` from inside LangGraph). It's a knowledge store, not a privileged service: the agent's credentials never traverse it, and a compromised sandbox can't pivot through Neo4j to LiteLLM or the API surface.

---

## Components

### LiteLLM Proxy (`decepticon-net`, port 4000)

Routes all LLM requests to provider backends (Anthropic, OpenAI, Google, MiniMax, DeepSeek, xAI, Mistral, OpenRouter, Nvidia NIM, Ollama, plus 6 subscription OAuth handlers). Provides:
- Unified API endpoint for all agents
- Automatic fallback chain when a provider is unavailable
- Usage tracking and rate limiting per provider
- Billing aggregation across models

Configuration: `config/litellm.yaml`. Dynamic model registration: `config/litellm_dynamic_config.py` (Ollama, custom gateways, ad-hoc overrides).

### LangGraph Platform (`decepticon-net`, port 2024)

Hosts and orchestrates all agents. Provides:
- Agent lifecycle management (spawn, execute, terminate)
- Event streaming via Server-Sent Events (SSE)
- State persistence between agent runs
- The LangGraph SDK endpoint consumed by both the CLI and Web Dashboard

### PostgreSQL (`decepticon-net`, port 5432)

Persistent relational storage for:
- LiteLLM virtual keys, spend logs, user budgets
- Web dashboard data (engagements, findings, OPPLAN objectives, defense actions)
- User accounts (EE mode) or the single local user (OSS mode)

Two logical databases: `litellm` (managed by LiteLLM) and `decepticon_web` (managed via Prisma in the web dashboard).

### Neo4j Knowledge Graph (`sandbox-net` + `decepticon-net`, port 7687 / browser 7474)

Graph database for the attack graph. Stores:
- Hosts, services, vulnerabilities, credentials, accounts
- Typed relationships (EXPLOITS, REQUIRES, MITIGATES, RESPONDS_TO)
- Attack chain paths for multi-hop planning
- Defense actions from the Offensive Vaccine loop

**Dual-homed by design**: the sandbox writes operational findings into the graph (`cypher-shell` from inside Kali), and the agent in LangGraph reads them back to plan the next objective. Both networks see the same Neo4j instance on the same `bolt://neo4j:7687` URI.

### Sandbox (`sandbox-net`)

Hardened Kali Linux container. Runs:
- All agent-issued bash commands (via persistent tmux sessions)
- Offensive tools: nmap, sqlmap, Impacket, Metasploit, Nuclei
- Sliver C2 client (`sliver-client`) with auto-generated operator config
- Interactive sessions for tools like `msfconsole`, `evil-winrm`

The sandbox is the only place where commands actually execute. LangGraph reaches it via the Docker socket, not the network.

### C2 Server (`sandbox-net`, Sliver)

Sliver team server runs alongside the sandbox on the operational network. Features:
- mTLS, HTTPS, and DNS-based C2 channels
- Implant generation (Windows, Linux, macOS)
- Session management for post-exploitation

Activated via `COMPOSE_PROFILES=c2-sliver` (default). Future profiles: `c2-havoc`.

### Web Dashboard (`decepticon-net`, port 3000 + terminal WebSocket on 3003)

Next.js 16 application providing a browser-based control plane. See [Web Dashboard](web-dashboard.md).

---

## Bash Tool & Interactive Sessions

Agents execute commands through a thin `bash` tool backed by `DockerSandbox.execute_tmux()`. Key behaviors:

**Persistent tmux sessions** — each named session persists across commands. An agent can open `msfconsole`, send commands into the session, and read output — the same way a human operator would.

**Interactive prompt detection** — when a tool presents an interactive prompt (`msf6 >`, `sliver >`, `PS C:\>`), the agent detects it and sends follow-up commands rather than waiting forever.

**Output management:**

| Output size | Handling |
|-------------|---------|
| ≤ 15K chars | Returned inline in the tool result |
| 15K – 100K chars | Saved to `/workspace/.scratch/`, summary returned |
| > 5M chars | Watchdog kills the command |

ANSI escape codes are stripped and repetitive output lines are compressed before being sent to the LLM.

---

## Data Flow: Single Objective

```
Orchestrator reads OPPLAN
        │
        ▼
  Pick next pending objective
        │
        ▼
  Spawn specialist agent (fresh context)
  ┌─────────────────────────────────────────────┐
  │  System prompt: RoE + skills + OPPLAN status │
  │  Tools: bash → sandbox (via Docker socket)   │
  │         read_file / write_file → workspace/  │
  │         kg_* → Neo4j (bolt://neo4j:7687)     │
  │         cve_lookup → NVD / OSV / EPSS APIs   │
  └─────────────────────────────────────────────┘
        │
        ▼
  Agent executes, writes findings to workspace/
        │
        ▼
  Returns PASSED | BLOCKED
        │
        ▼
  Orchestrator updates OPPLAN status
  Findings appended to disk
        │
        ▼
  Next objective (or Vaccine phase if all done)
```

---

## Security Boundaries

| Boundary | Enforcement |
|----------|-------------|
| Sandbox → Management services | Separate Docker networks; LiteLLM/PostgreSQL/LangGraph/Web are not routable from `sandbox-net` |
| LangGraph → Sandbox | Docker socket only (no TCP) |
| Sandbox → Neo4j | Allowed (intentional shared service for attack graph writes) |
| Credential isolation | Provider API keys live on `decepticon-net`; the sandbox never sees them |
| Host isolation | All commands run inside Docker; no host filesystem access except the engagement-scoped `/workspace` bind mount |
