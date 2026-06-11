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
│  (KGStore — dual-homed bolt:// for agent + sandbox writes)  │
│                     │       │                              │
│  BHCE       :8081   │       │                              │
│  BHCE-Neo4j (intl.) │       │                              │
│  (AD attack-graph sidecar, decepticon-net only)             │
└─────────────────────┘       └──────────────────────────────┘
       Management                       Operations
   (LLM, persistence, UI)        (exploitation, C2, targets)
```

**Network boundaries.** The sandbox cannot reach LiteLLM, PostgreSQL, the LangGraph API, the web dashboard, the BHCE API, or BHCE's Neo4j — none of the management services are routable from `sandbox-net`. The agent inside LangGraph cannot reach attack tooling over a TCP socket; the only channel into the sandbox is `docker exec` via the Docker socket bind-mount.

**KGStore Neo4j is the one cross-network shared service** — it sits on both networks because the sandbox writes findings into it (`bolt://neo4j:7687` from inside Kali) and the agent reads them back (`bolt://neo4j:7687` from inside LangGraph). It's a knowledge store, not a privileged service: the agent's credentials never traverse it, and a compromised sandbox can't pivot through Neo4j to LiteLLM or the API surface.

**BHCE has its own dedicated Neo4j** on `decepticon-net` only. Neo4j Community Edition allows one user database per server and KGStore already occupies it, so BHCE gets a separate instance to avoid label/constraint collisions with its `dawgs` driver. See [ADR-0005](adr/0005-bloodhound-via-bhce-rest-client.md). The sandbox does **not** see the BHCE Neo4j — the AD attack-graph pipeline is a management-plane concern only; the sandbox produces SharpHound ZIPs and hands them to the agent, never talks to BHCE directly.

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
- The single local user record

Two logical databases: `litellm` (managed by LiteLLM) and `decepticon_web` (managed via Prisma in the web dashboard).

### Neo4j Knowledge Graph — KGStore (`sandbox-net` + `decepticon-net`, port 7687 / browser 7474)

Graph database for the cross-domain attack graph (web, cloud, smart-contract findings plus the chain planner's view across all domains). Stores:
- Hosts, services, vulnerabilities, credentials, accounts
- Typed relationships (EXPLOITS, REQUIRES, AFFECTS, LEADS_TO)
- Attack chain paths for multi-hop planning

**Dual-homed by design**: the sandbox writes operational findings into the graph (`cypher-shell` from inside Kali), and the agent in LangGraph reads them back to plan the next objective. Both networks see the same Neo4j instance on the same `bolt://neo4j:7687` URI.

### BloodHound Community Edition sidecar (`decepticon-net`, BHCE API on host port 8081)

AD attack-graph layer, introduced by [ADR-0005](adr/0005-bloodhound-via-bhce-rest-client.md). Two containers:

- `bhce` — `docker.io/specterops/bloodhound` pinned to the v9.2.2 release commit. Speaks the official BHCE REST API (HMAC-signed, OpenAPI 3.0.3 at `/api/v2/spec`).
- `bhce-neo4j` — dedicated `neo4j:4.4.42-community` for BHCE's graph. No host port exposure; only the `bhce` container talks bolt to it.

Postgres is reused from the existing `postgres` container — `containers/postgres-init/02-bloodhound-db.sh` pre-creates the `bloodhound` database plus the `pg_trgm` extension so BHCE's goose migrations bootstrap cleanly on first boot.

Agents call BHCE through `decepticon.tools.ad.bh_tools.bhce_status` / `bhce_cypher` / `bhce_ingest_zip` and the shared `decepticon.tools.ad.bhce_client.BHCEClient` HMAC-3-chain signer. The in-house `bh_ingest_zip` / `adcs_post_process` / `dcsync_check` / `delegation_audit` / `gpo_audit` / `shadow_creds_audit` / `adcs_audit` tools emit `DeprecationWarning` on every call and will move to `decepticon.compat` next minor.

### Skillogy (`decepticon-net`, REST API on host port 9100)

Standalone skill catalog service introduced by [ADR-0008](adr/0008-skillogy-hard-acl-phase1a.md). Three pieces:

- A `python:3.13-slim`–based container (`containers/skillogy.Dockerfile`) running FastAPI over Uvicorn.
- A dedicated Neo4j graph (separate from the engagement KG above) holding `:Skill` nodes with edges derived from skill frontmatter (`BUILDS_ON`, `CHAINS_TO`, `MITRE_RELATED`, …).
- Three REST endpoints (`POST /v1/skills:find`, `POST /v1/skills:load`, `POST /v1/skills:traverse`) plus health (`GET /v1/health`) and a manager-of-coverage helper (`POST /v1/skills:moc`).

The graph is rebuilt from disk at container start. Skill source remains the `packages/decepticon/decepticon/skills/` directory tree (`standard/`, `shared/`, plus `plugins/` from third-party bundles). Adding a skill is a new `SKILL.md` file plus a graph rebuild — no schema migration.

Agents reach Skillogy through `SkillogyMiddleware`, which is a thin REST client. The middleware projects three agent-facing tools onto each role:

- `find_skill(query?, subdomain?, mitre_id?, tag?, tactic_id?, limit=20)` — AND-combined relationship-aware discovery, returns frontmatter only.
- `load_skill(name_or_path)` — fetches the body + frontmatter of one skill.
- `traverse(from_path, edge_types?, depth=2)` — explicit BFS from a seed skill.

Every middleware call carries an `allowed_path_prefixes` parameter set by the agent factory (e.g. `["skills/standard/ad/", "skills/shared/"]`); Skillogy enforces this hard ACL server-side, so prompt-injected widening attempts cannot escape the role's slice. Cross-role reads only succeed when the target lives under `skills/shared/`.

The Neo4j instance Skillogy uses is **not** the same as the engagement KGStore — they have different schemas, different write semantics, and run as separate containers so a long catalog rebuild can't lock engagement reads.

### Sandbox (`sandbox-net`)

Hardened Kali Linux container. Runs:
- All agent-issued bash commands (via persistent tmux sessions)
- Offensive tools: nmap, sqlmap, Impacket, Metasploit, Nuclei
- Sliver C2 client (`sliver-client`) with auto-generated operator config
- Interactive sessions for tools like `msfconsole`, `evil-winrm`

The sandbox is the only place where commands actually execute. LangGraph reaches it via the Docker socket, not the network.

### C2 Server (`sandbox-net`, Sliver — dynamic-spawn)

Sliver team server runs alongside the sandbox on the operational network. Features:
- mTLS, HTTPS, and DNS-based C2 channels
- Implant generation (Windows, Linux, macOS)
- Session management for post-exploitation

Brought up on demand by the orchestrator via `ops_start("c2-sliver")` after a foothold is gained — see [ADR-0006](adr/0006-agent-driven-container-lifecycle.md). Default `decepticon start` keeps the C2 plane cold. Future profile: `c2-havoc` (slated for a later release; the orchestrator's prompt and the opscontrol allowlist already accept it).

### Web Dashboard (`decepticon-net`, port 3000 + terminal WebSocket on 3003 — dynamic-spawn)

Next.js 16 application providing a browser-based control plane. v1.1.8 made this dynamic: it no longer comes up on `decepticon start`. From inside the CLI, run `/web` to spawn it; `/web url` prints the URL; `/web down` stops the container without removing it. See [Web Dashboard](web-dashboard.md).

### Dynamic Workload Lifecycle ([ADR-0006](adr/0006-agent-driven-container-lifecycle.md))

The orchestrator (and only the orchestrator) controls specialist infrastructure through three tools:

- `ops_start("<workload>")` — returns immediately with `state: "starting"`. The opscontrol daemon (a host-binary supervised by systemd / launchd) calls `docker compose --profile <workload> up -d` in a background goroutine and tracks the state machine `starting → running → stopped` per workload.
- `ops_status` — fallback for daemon reachability checks; routine polling is discouraged because the middleware below already delivers transitions.
- `ops_stop("<workload>")` — graceful shutdown via `docker compose stop`.

The `OpsControlNotificationMiddleware` polls the daemon's `/v1/profiles` socket once per turn and, when a workload's state changes, injects a `<system-reminder>` HumanMessage on the very next inference — so the agent learns about a BHCE cold-start completion (or failure) without polling. Same shape as Claude Code's background-bash auto-notification pattern.

Allowed workloads: `ad`, `c2-sliver`, `c2-havoc`, `reversing`, `cloud`, `mobile`, `phishing`, `forensics`, `ics`, `iot`, `supply-chain`, `wireless`. Today's compose ships sidecar services for `ad`, `c2-sliver`, and `reversing`; the rest of the allowlist names workloads whose specialist agents work directly inside the sandbox.

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

**Background commands + auto-notification** — long-running commands (`nmap -p- -A`, full Burp scans, fuzzers) launch with `run_in_background=True` and return immediately with a session handle. The LLM doesn't block on the prompt while the command runs. When the command finishes, `SandboxNotificationMiddleware` (in `packages/decepticon/decepticon/middleware/notifications.py`) polls the sandbox's `/read_session_log_diff` once per turn, captures the new output, and injects a `<system-reminder>` `HumanMessage` carrying the exit code and stdout/stderr diff onto the agent's very next inference. The agent doesn't have to call `bash_output()` — completion comes to it. Same shape as the `OpsControlNotificationMiddleware` workload-state pattern (ADR-0006), and same shape as Claude Code's native background-bash auto-notification.

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
| Sandbox → KGStore Neo4j | Allowed (intentional shared service for cross-domain attack graph writes) |
| Sandbox → BHCE API / BHCE Neo4j | Blocked — BHCE lives on `decepticon-net` only; the sandbox produces SharpHound ZIPs and hands them to the agent, which then ingests via `bhce_ingest_zip`. There is no sandbox-side bolt or REST path into BHCE. |
| Credential isolation | Provider API keys + the BHCE HMAC token live on `decepticon-net`; the sandbox never sees them |
| Host isolation | All commands run inside Docker; no host filesystem access except the engagement-scoped `/workspace` bind mount |
