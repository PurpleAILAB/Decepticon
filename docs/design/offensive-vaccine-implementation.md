# Offensive Vaccine — Implementation Design

**Status:** Accepted  
**Author:** Decepticon Core Team  
**Date:** 2026-06-29  
**Components:** `agents/standard/vaccine.py`, `tools/vaccine/`, `middleware/vaccine.py`, `skills/plugins/vaccine/`

---

## 1. Executive Summary

The Offensive Vaccine system closes the gap between offensive discovery and defensive hardening within a single engagement lifecycle. Where the Red Cell discovers vulnerabilities and the Blue Cell validates detection coverage, the Vaccine agent occupies the space between: it takes each confirmed Finding, generates a remediation plan, deploys compensating controls, and re-executes the original attack vector to prove the defence holds. The result is a closed-loop provenance chain — from initial exploitation through remediation to verified mitigation — that gives stakeholders cryptographic-grade confidence that each vulnerability was not merely reported but *resolved*.

This document describes the architecture, data model, agent design, tool surface, middleware integration, skill decomposition, and operational considerations for the Offensive Vaccine subsystem.

## 2. Motivation and Problem Statement

Traditional penetration testing produces a report. The report describes vulnerabilities, assigns severity ratings, and offers remediation guidance. The customer then implements fixes — or doesn't. Months later, a retest may or may not confirm the fixes. This model has three systemic failures:

1. **Temporal disconnect.** The gap between discovery and remediation is measured in weeks or months, during which the vulnerability remains exploitable.
2. **Verification gap.** Remediation advice is often generic ("apply the vendor patch," "restrict network access") and is never verified against the *specific* attack vector that proved the vulnerability.
3. **Provenance loss.** There is no machine-readable chain linking the original finding to the specific defence deployed and the verification that proved it effective.

The Offensive Vaccine eliminates all three by executing remediation *within* the engagement, using the engagement's own tooling, and recording every step in the knowledge graph.

## 3. Architecture Overview

### 3.1 Position in the Agent Hierarchy

The Vaccine agent sits alongside the Blue Cell in the post-exploitation phase of an engagement:

```
Red Cell (attack) → Detector (Sigma rules) → Blue Cell (detection coverage)
                 ↘                                        ↗
                   Vaccine (remediate → verify) ─────────┘
```

The Red Cell produces Findings. The Vaccine agent consumes them. Its output — `Mitigation`, `DefenseAction`, and `VerificationResult` nodes — feeds back into the Blue Cell's Defense Brief, enriching the coverage report with proven mitigations.

### 3.2 Data Flow

```
Finding ──→ generate_remediation_brief ──→ Mitigation (planned)
                                                │
                                                ↓
                                          apply_defense ──→ DefenseAction (deployed)
                                                │
                                                ↓
                                          verify_defense ──→ VerificationResult (pending)
                                                │
                                                ↓
                                     record_vaccine_result ──→ VerificationResult (blocked|bypassed|partial)
                                                │                     │
                                                ↓                     ↓
                                          Finding.vaccine_status    Mitigation.status = "verified"
```

Each step is atomic, idempotent (MERGE semantics), and independently auditable.

### 3.3 Component Map

| Component | Path | Responsibility |
|-----------|------|---------------|
| Agent factory | `agents/standard/vaccine.py` | Wires tools, middleware, prompt; produces compiled LangGraph agent |
| Tools | `tools/vaccine/tools.py` | Four LangChain `@tool` functions operating on the KG |
| Middleware | `middleware/vaccine.py` | Injects live vaccine state into every LLM turn |
| Skills | `skills/plugins/vaccine/` | Router + three sub-skills for the Claude skill system |
| KG schema | `skills/.graph/vaccine-defense-schema.cypher` | Idempotent Cypher for node/edge types |

## 4. Knowledge Graph Schema

The Vaccine subsystem introduces three new node types and four new edge types into the engagement knowledge graph.

### 4.1 Node Types

**Mitigation**
Represents a planned or completed remediation effort for a specific Finding. Properties:

- `status`: `planned` → `deployed` → `verified` (or `failed`)
- `finding_id`: back-reference to the addressed Finding
- `severity`: inherited from the Finding
- `techniques`: list of ATT&CK technique IDs involved
- `created_at`: ISO-8601 timestamp

**DefenseAction**
Represents a single compensating control deployed as part of a Mitigation. Properties:

- `action_type`: enumerated category — `firewall_rule`, `config_change`, `detection_rule`, `code_patch`, `other`
- `description`: human-readable description
- `configuration`: raw rule body / config diff
- `deployed_at`: ISO-8601 timestamp
- `status`: `deployed` (immutable after creation; superseded by new actions)

**VerificationResult**
Represents the outcome of re-executing an attack vector against a defended target. Properties:

- `disposition`: `pending` → `blocked` | `bypassed` | `partial`
- `attack_replay_command`: the exact command or tool invocation replayed
- `evidence`: raw stdout/stderr or log excerpt proving the disposition
- `verified_at`: ISO-8601 timestamp
- `finalised_at`: ISO-8601 timestamp (set when disposition is terminal)

### 4.2 Edge Types

| Edge | Source → Target | Meaning |
|------|----------------|---------|
| `ADDRESSES` | Mitigation → Finding | "this mitigation addresses this finding" |
| `MITIGATES` | DefenseAction → Finding | "this control mitigates this finding" |
| `IMPLEMENTS` | DefenseAction → Mitigation | "this action implements this mitigation plan" |
| `VERIFIES` | VerificationResult → DefenseAction | "this test verifies this control" |
| `TESTED` | VerificationResult → Finding | "this test re-targeted this finding" |

### 4.3 Idempotency

All graph mutations use MERGE semantics. Running the same tool with the same parameters produces the same graph state. This is critical for:

- **Retry safety:** a failed LLM turn can be retried without creating duplicate nodes.
- **Multi-agent coordination:** if both the Vaccine agent and a human operator create a DefenseAction for the same Finding, MERGE prevents collisions.
- **Auditability:** the graph is append-only in practice; node properties accumulate, never conflict.

## 5. Agent Design

### 5.1 Factory Pattern

`create_vaccine_agent()` follows the same factory signature as `create_blue_cell_agent()`:

```python
def create_vaccine_agent(
    *,
    backend=None,
    llm=None,
    fallback_models=None,
    tools=None,
    middleware=None,
    system_prompt=None,
    recursion_limit=None,
) -> CompiledGraph:
```

Every parameter is optional. When `None`, the factory builds the OSS baseline and applies plugin overrides from the `decepticon.bundles` entry-point group. When provided, the value fully replaces the baseline — no merging.

### 5.2 System Prompt

The system prompt encodes the attack→defend→verify loop as a four-phase protocol:

1. **Assess** — query the KG for unmitigated Findings, prioritise by severity and exploitability.
2. **Remediate** — generate a brief, then deploy the recommended control.
3. **Verify** — replay the original attack; iterate if the defence fails.
4. **Report** — summarise proven coverage and residual risk.

The prompt explicitly constrains the agent: it must not discover new attack surface (that is the Red Cell's job), and it must not claim a defence is proven without a passing verification.

### 5.3 Recursion Limit

The Vaccine agent has a higher recursion limit (150 vs. Blue Cell's 120) because the attack→defend→verify loop can require multiple iterations per Finding. A single Finding might need:

- 1 turn to generate the brief
- 1 turn to deploy the control
- 1 turn to verify
- 1+ turns to iterate if verification fails

With 20 unmitigated Findings, the agent may need 80–120 turns.

### 5.4 Tool Surface

The agent receives seven tools:

| Tool | Source | Purpose |
|------|--------|---------|
| `generate_remediation_brief` | `tools/vaccine/` | Produce the structured fix plan |
| `apply_defense` | `tools/vaccine/` | Deploy a compensating control |
| `verify_defense` | `tools/vaccine/` | Re-execute the attack vector |
| `record_vaccine_result` | `tools/vaccine/` | Finalise the verification outcome |
| `kg_query` | `tools/research/` | Ad-hoc SPARQL/Cypher queries |
| `kg_neighbors` | `tools/research/` | Graph traversal |
| `kg_stats` | `tools/research/` | Engagement statistics |

The KG research tools give the agent read access to the full graph for situational awareness without needing to enumerate every Finding manually.

## 6. Middleware

### 6.1 VaccineStateMiddleware

The middleware solves the context-window problem: after many turns the LLM loses track of which Findings have been addressed and which remain. The middleware queries the KG at the start of every turn and injects a structured summary as a `SystemMessage`:

```json
{
  "unmitigated_findings": [...],
  "active_defense_actions": [...],
  "recent_verifications": [...],
  "summary": {
    "total_findings": 42,
    "unmitigated": 17,
    "mitigated": 25,
    "coverage_pct": 59.5
  }
}
```

This ensures the agent always has accurate state even after context-window compaction or long multi-turn sessions.

### 6.2 Caps

To avoid blowing the context window on large engagements:

- `max_findings=20`: only the 20 highest-priority unmitigated Findings are injected.
- `max_history=10`: only the 10 most recent verification results are shown.

The agent can always use `kg_query` to access the full dataset.

## 7. Skill Decomposition

The Vaccine capability is exposed through the Claude skill system as a router skill with three sub-skills:

### 7.1 Router Skill (`vaccine/SKILL.md`)

Determines which sub-skill to invoke based on the user's intent:

- "remediate," "fix," "patch," "mitigate" → `remediation-brief`
- "deploy," "apply," "enforce" → `defense-execution`
- "verify," "test," "prove," "retest" → `verify-defense`

### 7.2 Remediation Brief (`vaccine/remediation-brief/SKILL.md`)

Orchestrates `generate_remediation_brief` for one or more Findings. Handles prioritisation, batching, and formatting of the output brief.

### 7.3 Defense Execution (`vaccine/defense-execution/SKILL.md`)

Orchestrates `apply_defense` with pre-flight checks (is the Finding still unmitigated? does a Mitigation exist?) and post-deployment validation (did the KG update correctly?).

### 7.4 Verify Defense (`vaccine/verify-defense/SKILL.md`)

Orchestrates `verify_defense` and `record_vaccine_result` in sequence. Handles the iteration loop: if verification fails, feeds the failure evidence back into a new remediation cycle.

## 8. Security Considerations

### 8.1 Blast Radius

The Vaccine agent deploys changes to the target environment. Unlike the read-only Blue Cell, it has write access. Mitigations:

- **Sandbox isolation.** All defences are deployed within the engagement sandbox, never on production infrastructure directly.
- **Rollback capability.** Each `DefenseAction` records its `configuration`, enabling automated rollback if needed.
- **Approval gates.** In production deployments, the `apply_defense` tool can be wrapped with an approval middleware that requires human sign-off before deploying controls rated above a configurable severity threshold.

### 8.2 Attack Replay Safety

`verify_defense` re-executes attack vectors. This is inherently dangerous. Safety controls:

- The replay runs within the same sandbox that the Red Cell used — same network isolation, same monitoring.
- The `attack_replay_command` is recorded in the KG for full auditability.
- The agent cannot craft *new* attacks — it replays vectors from the engagement's provenance chain.

### 8.3 Privilege Escalation

The Vaccine agent does not receive `bash` directly. Defence deployment is mediated through `apply_defense`, which records every action. The sandbox backend enforces privilege boundaries.

## 9. Integration with Existing Components

### 9.1 Defense Brief

The Blue Cell's `defense_brief` tool already reads the KG. Vaccine-created `DefenseAction` and `VerificationResult` nodes are automatically included in the coverage calculation without any changes to the Blue Cell codebase.

### 9.2 ATT&CK Navigator

Techniques with verified mitigations (`vaccine_status == "mitigated"`) appear as a third colour tier in the Navigator layer: green (detected), blue (mitigated), red (gap).

### 9.3 SubAgent Protocol

The `SUBAGENT_SPEC` allows the Decepticon orchestrator to spawn the Vaccine agent as a sub-agent after the Red Cell completes its offensive phase. The `parent_agents=("decepticon",)` binding ensures it appears in the orchestrator's available-agent roster.

## 10. Operational Runbook

### 10.1 Typical Engagement Flow

1. Red Cell completes offensive operations; Findings are in the KG.
2. Operator invokes the Vaccine agent (or the orchestrator spawns it automatically).
3. Vaccine middleware injects the unmitigated-Finding list.
4. Agent iterates: brief → deploy → verify for each Finding by severity.
5. Agent reports final coverage: "23/25 Findings mitigated; 2 require manual intervention (kernel-level, out of sandbox scope)."
6. Blue Cell produces the Defense Brief, now reflecting vaccine-proven mitigations.

### 10.2 Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Verification fails (bypassed) | Finding remains unmitigated | Agent iterates with a different defence strategy |
| KG unavailable | Middleware injects empty state | Agent falls back to `kg_query` tools; if KG is fully down, agent reports the blocker |
| Sandbox timeout | Verification result stays `pending` | Agent retries; after 3 failures, escalates to operator |
| Context window exhaustion | Agent loses track of progress | Middleware re-injects state; agent resumes from the KG truth |

### 10.3 Monitoring

- **Coverage metric:** `mitigated / total_findings` — tracked in the middleware summary and exposed via `kg_stats`.
- **Iteration count:** average verification attempts per Finding — a high number indicates the agent's remediation strategy needs tuning.
- **Time-to-mitigate:** elapsed time from Finding creation to `vaccine_status == "mitigated"`.

## 11. Future Work

1. **Automated rollback.** If a defence causes service disruption (detected via health-check integration), automatically revert the `DefenseAction` and mark it `rolled_back`.
2. **Cross-engagement learning.** Successful defence patterns (e.g., "for SQLi on Apache/PHP, deploy ModSecurity rule X") can be extracted from the KG and pre-loaded into future engagements as a remediation knowledge base.
3. **Human-in-the-loop approval.** For high-severity defences (privilege changes, firewall modifications), insert an approval gate that pauses the agent until a human operator confirms.
4. **Parallel remediation.** Currently the agent processes Findings sequentially. A future version could spawn parallel vaccine sub-agents per Finding or per host, bounded by a global concurrency limit.
5. **Regression testing.** After all Findings are mitigated, run a full regression pass re-executing *every* original attack vector to catch defence interactions (e.g., fixing one vulnerability re-opens another).

## 12. Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| MERGE semantics for all KG writes | Idempotency is non-negotiable for retry safety and multi-agent coordination | Bare CREATE (rejected: duplicate risk), upsert-by-query (rejected: more complex, same effect) |
| Higher recursion limit (150) | The attack→defend→verify loop multiplies turns vs. read-only agents | Same as Blue Cell (120, rejected: too tight for 20+ Findings), unlimited (rejected: runaway risk) |
| Middleware state injection | Keeps the agent grounded after context compaction | Tool-based refresh (rejected: agent must remember to call it), prompt-stuffing (rejected: stale after turn 1) |
| Separate tool for `record_vaccine_result` | Decouples verification execution from result recording; allows human-in-the-loop disposition override | Combined verify+record (rejected: no approval gate possible), event-driven (rejected: overengineered for v1) |
| Sandbox-mediated replay | Attack replay inherits the Red Cell's isolation boundary | Direct bash (rejected: no isolation), mock replay (rejected: doesn't prove anything) |

---

*This document describes the Offensive Vaccine subsystem as implemented in the `standard` bundle. Plugin authors can override any component via the `decepticon.bundles` entry-point group.*
