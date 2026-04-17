# Architecture

## Overview

Decepticon runs on two completely isolated Docker networks. Management infrastructure (LLM proxy, databases, agent API) and operational infrastructure (sandbox, C2, targets) share zero network access. The only bridge is the Docker socket — LangGraph controls the sandbox exclusively through it.

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
           │                             │ Docker socket only
┌──────────▼──────────┐       ┌──────────▼──────────────────┐
│   decepticon-net    │       │       sandbox-net            │
│                     │       │                              │
│  LiteLLM  :4000     │       │  Sandbox (Kali Linux)        │
│  PostgreSQL :5432   │       │  Neo4j        :7687/:7474    │
│  LangGraph  :2024   │       │  C2 Server    (Sliver)       │
│  Web        :3000   │       │  Victim targets              │
└─────────────────────┘       └──────────────────────────────┘
       Management                       Operations
   (LLM, persistence, UI)        (exploitation, C2, targets)
```

**No cross-network access.** Services on `decepticon-net` cannot reach `sandbox-net` and vice versa. LangGraph communicates with the sandbox exclusively via the Docker socket — not the network.

---

## Components

### LiteLLM Proxy (`decepticon-net`, port 4000)

Routes all LLM requests to Anthropic, OpenAI, and Google backends. Provides:
- Unified API endpoint for all agents
- Automatic failover when a provider is unavailable
- Usage tracking and rate limiting per provider
- Billing aggregation across models

Configuration: `config/litellm.yaml`

### LangGraph Platform (`decepticon-net`, port 2024)

Hosts and orchestrates all agents. Provides:
- Agent lifecycle management (spawn, execute, terminate)
- Event streaming via Server-Sent Events (SSE)
- State persistence between agent runs
- The LangGraph SDK endpoint consumed by both CLI and Web Dashboard

### PostgreSQL (`decepticon-net`, port 5432)

Persistent relational storage for:
- Engagement records
- Finding metadata
- OPPLAN objectives and status
- User accounts (EE mode) or the single local user (OSS mode)

Managed via Prisma ORM in the web dashboard.

### Neo4j Knowledge Graph (`sandbox-net`, port 7687 / browser 7474)

Graph database for the attack graph. Stores:
- Hosts, services, vulnerabilities, credentials, accounts
- Typed relationships (EXPLOITS, REQUIRES, MITIGATES, RESPONDS_TO)
- Attack chain paths for multi-hop planning
- Defense actions from the Offensive Vaccine loop

Lives on `sandbox-net` because it stores operational findings that must not cross to management infrastructure.

### Sandbox (`sandbox-net`)

Hardened Kali Linux container. Runs:
- All agent-issued bash commands (via persistent tmux sessions)
- Offensive tools: nmap, sqlmap, Impacket, Metasploit, nuclei
- Sliver C2 client (`sliver-client`) with auto-generated operator config
- Interactive sessions for tools like `msfconsole`, `evil-winrm`

The sandbox is the only place where commands actually execute. LangGraph reaches it via Docker socket, not the network.

### C2 Server (`sandbox-net`, Sliver)

Sliver team server runs alongside the sandbox on the operational network. Features:
- mTLS, HTTPS, and DNS-based C2 channels
- Implant generation (Windows, Linux, macOS)
- Session management for post-exploitation

Activated via `COMPOSE_PROFILES=c2-sliver` (default). Future profiles: `c2-havoc`.

### Web Dashboard (`decepticon-net`, port 3000)

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
  ┌─────────────────────────────────────┐
  │  System prompt: RoE + skills + OPPLAN status  │
  │  Tools: bash → sandbox (via Docker socket)    │
  │         read_file / write_file → workspace/   │
  │         kg_* → Neo4j (bolt://neo4j:7687)      │
  │         cve_lookup → NVD / OSV / EPSS APIs    │
  └─────────────────────────────────────┘
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
| Sandbox ↔ Management | Separate Docker networks, no routing |
| LangGraph ↔ Sandbox | Docker socket only (no network port) |
| Agent commands | `SafeCommandMiddleware` blocks destructive ops |
| Credential isolation | API keys live on `decepticon-net`; sandbox never sees them |
| Host isolation | All commands run inside Docker; no host filesystem access |
