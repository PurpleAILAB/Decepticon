# Agents

Decepticon ships **17 specialist agents** organized by kill chain phase. Each agent starts with a **fresh context window** per objective — no accumulated noise, no context degradation. Findings persist to disk (`workspace/`) and the knowledge graph, not agent memory.

---

## Agent Roster

### Orchestrators

| Agent | Role |
|-------|------|
| **Decepticon** | Main red-team orchestrator. Reads the OPPLAN, dispatches objectives to specialist sub-agents, and tracks status transitions. Sub-agents: `recon`, `exploit`, `postexploit`, `analyst`, `reverser`, `contract_auditor`, `cloud_hunter`, `ad_operator`. |
| **Vulnresearch** | Vulnerability research orchestrator — runs the five-stage pipeline (`scanner → detector → verifier → exploiter → patcher`) with state passed between stages exclusively through the knowledge graph. |
| **Soundwave** | Engagement planner. Standalone graph (not a sub-agent of Decepticon). Interviews the operator and generates RoE, ConOps, Deconfliction Plan, and OPPLAN. |

### Reconnaissance

| Agent | Role |
|-------|------|
| **Recon** | Port scanning, service enumeration, DNS, subdomain discovery, OSINT. Populates the knowledge graph with hosts and services. |

### Vulnerability Research Pipeline

Sub-agents of the **Vulnresearch** orchestrator. State flows between stages via the knowledge graph; each stage runs with fresh context.

| Stage | Agent | Output |
|-------|-------|--------|
| Discovery | **Scanner** | Vulnerability candidates with CVE/CVSS |
| Analysis | **Detector** | Confidence-rated findings, detection rules |
| Confirmation | **Verifier** | Verified findings (2+ methods for CRITICAL/HIGH) |
| Exploitation | **Exploiter** | Working proof-of-concept |
| Remediation | **Patcher** | Patch code or configuration fix |

### Exploitation & Post-Exploitation

| Agent | Role |
|-------|------|
| **Exploit** | Initial access and exploitation tactics. Web/AD attacks (SQLi, SSTI, Kerberoasting, ADCS abuse, credential attacks). |
| **Post-Exploit** | Privilege escalation, lateral movement, credential harvesting, persistence. Operates via C2 sessions once initial access is established. |

### Defense

| Agent | Role |
|-------|------|
| **Defender** | Standalone graph for the Offensive Vaccine loop. Receives a defense brief for each finding, applies mitigations, and tracks results in the knowledge graph. |

### Domain Specialists

| Agent | Role |
|-------|------|
| **AD Operator** | Active Directory attacks — Kerberoasting, AS-REP roasting, ADCS ESC1-ESC15, DCSync, BloodHound path analysis. |
| **Cloud Hunter** | Cloud infrastructure attacks — IAM privilege escalation, S3 bucket exposure, Kubernetes RBAC escapes, metadata service abuse. |
| **Contract Auditor** | Solidity / EVM smart contract audits — reentrancy, oracle manipulation, flash loan abuse, access control. |
| **Reverser** | Binary analysis and reverse engineering — ELF/PE/Mach-O triage, packer detection, ROP gadget inventories, Ghidra/radare2 recon. |
| **Analyst** | Vulnerability research and reporting — source code review, static analysis (semgrep/bandit/gitleaks), dependency CVE sweeps, multi-hop exploit chain construction. |

---

## Fresh Context Model

Every specialist agent runs with a **clean context window** for each objective:

- The orchestrator picks the next pending objective from the OPPLAN
- A new agent instance is spawned with only what it needs: the objective, RoE guard rails, and relevant findings from disk
- The agent executes, writes findings to `workspace/`, and returns a `PASSED` or `BLOCKED` signal
- The orchestrator updates the OPPLAN and moves to the next objective

This prevents context window bloat and token accumulation across a long engagement.

---

## Middleware Stack

Each agent runs with a configurable middleware stack. Middleware is applied in order before each LLM call.

| Middleware | Purpose |
|------------|---------|
| `EngagementContextMiddleware` | Injects engagement metadata (slug, target, RoE summary) into the system prompt for the orchestrator. |
| `DecepticonSkillsMiddleware` | Loads SKILL.md frontmatter at startup, filters by agent role, and injects matching skill descriptions into the system prompt. Full skill content is fetched on demand via `read_file`. |
| `FilesystemMiddlewareNoExecute` | Provides `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep` tools backed by the sandbox filesystem. Execute is intentionally disabled — agents use the dedicated `bash` tool for command execution. |
| `SubAgentMiddleware` | Allows orchestrators (Decepticon, Vulnresearch) to delegate objectives to specialist sub-agents via the `task()` tool. |
| `OPPLANMiddleware` | Injects the current OPPLAN progress table into every LLM call and provides 5 CRUD tools for objective management (Claude Code V2 Task pattern). |
| `ModelFallbackMiddleware` | Switches to a fallback model on provider outage, rate limit, or context overflow. Walks the fallback chain built from the user's credentials inventory. |
| `SummarizationMiddleware` | Auto-compacts conversation history when the context window approaches capacity. |
| `AnthropicPromptCachingMiddleware` | Caches static system prompt content for Anthropic models to reduce token costs. Silently no-ops on non-Anthropic providers. |
| `PatchToolCallsMiddleware` | Sanitizes and normalizes tool call formats for compatibility across model providers (e.g. repairs dangling tool calls). |

### Stack per Agent Role

**Decepticon (Orchestrator)** — full stack with engagement context and sub-agent dispatch.

```
EngagementContext → Skills → FilesystemNoExecute → SubAgent → OPPLAN
                  → ModelFallback → Summarization → AnthropicPromptCaching → PatchToolCalls
```

**Vulnresearch (Orchestrator)** — same as Decepticon but without `EngagementContextMiddleware`.

```
Skills → FilesystemNoExecute → SubAgent → OPPLAN
       → ModelFallback → Summarization → AnthropicPromptCaching → PatchToolCalls
```

**Specialist sub-agents (Recon, Exploit, Post-Exploit, Scanner, Detector, etc.)**

```
Skills → FilesystemNoExecute
       → ModelFallback → Summarization → AnthropicPromptCaching → PatchToolCalls
```

Specialists also have the `bash` tool for command execution inside the sandbox; `FilesystemMiddlewareNoExecute` covers all file I/O.

**Soundwave (Planner)** — no `bash`, no sub-agents (document generation only).

```
Skills → FilesystemNoExecute
       → ModelFallback → Summarization → AnthropicPromptCaching → PatchToolCalls
```
