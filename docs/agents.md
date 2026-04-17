# Agents

Decepticon uses 16 specialist agents organized by kill chain phase. Each agent starts with a **fresh context window** per objective — no accumulated noise, no context degradation. Findings persist to disk (`workspace/`) and the knowledge graph, not agent memory.

---

## Agent Roster

### Orchestration

| Agent | Role |
|-------|------|
| **Decepticon** | Main orchestrator. Manages OPPLAN state, dispatches objectives to specialist agents, tracks dependencies and status transitions. |
| **Soundwave** | Engagement planner. Interviews the operator and generates RoE, ConOps, Deconfliction Plan, and OPPLAN. Also handles threat actor profiling. |

### Reconnaissance

| Agent | Role |
|-------|------|
| **Recon** | Port scanning, service enumeration, DNS resolution, subdomain discovery, and OSINT. Populates the knowledge graph with hosts and services. |
| **Scanner** | Automated vulnerability scanning (Nuclei, Nessus-compatible). Rates findings by severity, maps to CVEs, and seeds the KG. |

### Exploitation

| Agent | Role |
|-------|------|
| **Exploit** | Initial access and exploitation tactics. Executes attack chains based on findings from Recon and Scanner. |
| **Exploiter** | Proof-of-concept generation. Produces verified, working exploits for confirmed vulnerabilities. |
| **Detector** | Vulnerability detection and analysis. Generates detection rules and rates confidence/severity. |
| **Verifier** | Confirms vulnerabilities are real using two independent methods before escalating CRITICAL or HIGH findings. |
| **Patcher** | Generates remediation code and configuration fixes for verified vulnerabilities. |

### Post-Exploitation

| Agent | Role |
|-------|------|
| **Post-Exploit** | Privilege escalation, lateral movement, credential harvesting, and persistence. Operates via C2 sessions once initial access is established. |

### Defense

| Agent | Role |
|-------|------|
| **Defender** | Executes the Offensive Vaccine loop. Receives a defense brief for each finding, applies mitigations, and tracks results in the knowledge graph. |

### Domain Specialists

| Agent | Role |
|-------|------|
| **AD Operator** | Active Directory attacks — Kerberoasting, Pass-the-Hash, DCSync, BloodHound path analysis. |
| **Cloud Hunter** | Cloud infrastructure attacks — IAM privilege escalation, S3 bucket exposure, metadata service abuse. |
| **Contract Auditor** | Smart contract and blockchain security analysis. |
| **Reverser** | Binary analysis and reverse engineering. Integrates with static and dynamic analysis tools. |
| **Analyst** | Research, data aggregation, and final report generation. Queries the knowledge graph to produce executive summaries and technical findings. |

---

## Vulnerability Research Pipeline

The five exploitation agents form a sequential pipeline from discovery to remediation:

```
Scanner → Detector → Verifier → Exploiter → Patcher
```

| Stage | Agent | Output |
|-------|-------|--------|
| Discovery | Scanner | Vulnerability candidates with CVE/CVSS |
| Analysis | Detector | Confidence-rated findings, detection rules |
| Confirmation | Verifier | Verified findings (2+ methods for CRITICAL/HIGH) |
| Exploitation | Exploiter | Working proof-of-concept |
| Remediation | Patcher | Patch code or configuration fix |

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
| `SkillsMiddleware` | Loads skill frontmatter at startup, filters by agent role, injects matching skills into the system prompt. Full skill content available on-demand. |
| `FilesystemMiddleware` | Provides `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep` tools backed by the sandbox or host filesystem. |
| `SafeCommandMiddleware` | Blocks session-destroying commands (`pkill`, `killall`, `rm -rf /`, `nsenter`, `docker exec`). |
| `SubAgentMiddleware` | Allows the orchestrator to delegate objectives to specialist agents. |
| `OPPLANMiddleware` | Injects the current OPPLAN progress table into every LLM call. Provides CRUD tools for objective management. |
| `ModelFallbackMiddleware` | Switches to a fallback model on provider outage or rate limit. |
| `SummarizationMiddleware` | Compresses conversation history when the context window approaches capacity. |
| `PromptCachingMiddleware` | Caches static system prompt content to reduce token costs. |
| `PatchToolCallsMiddleware` | Sanitizes and normalizes tool call formats for compatibility across model providers. |

### Stack per Agent Role

**Decepticon (Orchestrator)**
```
SafeCommand → Skills → Filesystem → SubAgent → OPPLAN → ModelFallback → Summarization → PromptCaching → PatchToolCalls
```

**Soundwave (Planner)**
```
Skills → Filesystem → ModelFallback → Summarization → PromptCaching → PatchToolCalls
```

**Specialist agents (Recon, Exploit, Post-Exploit, etc.)**
```
Skills → Filesystem → SafeCommand → ModelFallback → Summarization → PromptCaching → PatchToolCalls
```
