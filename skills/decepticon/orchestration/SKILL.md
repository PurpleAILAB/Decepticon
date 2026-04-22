---
name: orchestration
description: "Decepticon orchestrator patterns — delegation, state management, adaptive re-planning, context handoff protocols."
allowed-tools: Read
metadata:
  subdomain: orchestration
  when_to_use: "delegate, orchestrate, next objective, blocked, re-plan, hand off, engagement state, status update, parallel execution"
  tags: orchestration, delegation, state-management, re-planning, context-handoff
  mitre_attack: []
---

# Decepticon Orchestration Patterns

## Delegation Protocol

### Context Handoff — What Every Sub-Agent Needs
Every `task()` delegation MUST include:

1. **Objective** — What specifically to accomplish (from OPPLAN)
2. **Scope** — IN SCOPE targets + OUT OF SCOPE boundaries (from RoE)
3. **Context** — Relevant findings from previous phases
4. **Lessons** — Known gotchas, failed approaches, OPSEC warnings
5. **Acceptance Criteria** — How the sub-agent knows it's done
6. **Output Location** — Where to save results (e.g. `recon/`, `exploit/`)

### Delegation Template
```
task(
  description="""
  OBJECTIVE: {objective_id} — {title}
  PHASE: {phase}

  SCOPE:
  - IN: {in_scope_targets}
  - OUT: {out_of_scope_targets}

  CONTEXT FROM PREVIOUS PHASES:
  {relevant_findings_summary}

  LESSONS LEARNED:
  {known_gotchas}

  ACCEPTANCE CRITERIA:
  - [ ] {criterion_1}
  - [ ] {criterion_2}

  Save all results to {phase}/
  """,
  subagent_type="{agent_name}"
)
```

### Sub-Agent Selection Matrix

| Objective Phase | Sub-Agent | When to Use |
|----------------|-----------|-------------|
| Planning | `soundwave` | Missing roe.json/conops.json/deconfliction.json, or documents need updating |
| Recon | `recon` | Subdomain/port/service enumeration, OSINT, cloud/web recon |
| Exploitation | `exploit` | Initial access: SQLi, SSTI, AD attacks, credential exploitation |
| Post-Exploitation | `postexploit` | After foothold: cred dump, privesc, lateral movement, C2 |

### Parallel Execution
Delegate independent tasks simultaneously for efficiency:
```
# Independent targets — run in parallel
task(description="Recon subnet 10.0.0.0/24...", subagent_type="recon")
task(description="Recon subnet 10.0.1.0/24...", subagent_type="recon")

# DO NOT parallelize dependent tasks:
# ✗ Exploit before recon completes
# ✗ PostExploit before foothold established
```

## State Management

### Engagement State Files
```
./
├── roe.json              # Immutable scope boundaries (read every iteration)
├── conops.json           # Operation concept
├── deconfliction.json    # Deconfliction identifiers and procedures
├── opplan.json           # Objective tracker (update status after each sub-agent)
├── findings.json         # Append-only discovery log
├── lessons_learned.md    # Failed approaches + what worked
└── .ralph_state.json     # Loop iteration counter + completion flags
```

### State Update Protocol (After Each Sub-Agent Returns)
1. **Parse result** — Did the sub-agent report PASSED or BLOCKED?
2. **Update opplan.json** — Set objective status (`passed`, `blocked`, `in_progress`)
3. **Append findings.json** — Add new discoveries with timestamp + source objective
4. **Append lessons_learned.md** — Record what worked, what failed, and why
5. **Check completion** — All objectives passed? → Generate summary

### Context Window Budget
- Read findings.json each iteration (keep last ~3000 chars)
- Summarize verbose sub-agent outputs before appending to findings
- Use files on disk as persistent memory — don't rely on conversation history

## Adaptive Re-planning

### When an Objective is BLOCKED
```
1. Document failure:
   - WHY it failed (specific error, defense mechanism, missing prerequisite)
   - WHAT was attempted (tools, techniques, targets)
   → Append to lessons_learned.md

2. Assess alternatives:
   - Different attack vector from findings?
   - Lower-risk approach?
   - Skip and return later after more intel?

3. Decision:
   IF alternative exists → delegate new task with adjusted approach
   IF prerequisite missing → re-order objectives (e.g., need more recon)
   IF no path forward → mark BLOCKED with explanation, move to next objective
```

### Re-ordering Objectives
The OPPLAN defines priority order, but you may deviate when:
- A higher-priority objective depends on a lower-priority one
- New findings reveal a faster path to the same goal
- An objective is temporarily blocked and others are actionable

Always document re-ordering decisions in lessons_learned.md.

## Response Format

### After Each Sub-Agent Completes
Report structured status:

| Objective | Phase | Sub-Agent | Result | Key Findings |
|-----------|-------|-----------|--------|-------------|
| OBJ-001 | Recon | recon | PASSED | 12 subdomains, AD on 10.0.0.5 |

### Decision Transparency
Before each delegation, briefly state:
- **Why** this objective is next (priority, dependency, re-plan reason)
- **Which** sub-agent and why
- **What** context you're passing

### Progress Summary
Maintain running status after each iteration:
```
Engagement: {name}
Progress: {passed}/{total} objectives
Current: OBJ-003 (Exploit phase)
Blocked: OBJ-002 (WAF blocking SQLi — will retry after credential access)
Next: OBJ-004 (PostExploit — pending OBJ-003 completion)
```

### Engagement Completion Report
When all objectives are done:
1. Full attack path (every hop, credential, escalation)
2. Credential inventory
3. Host access map
4. Recommendations for defensive improvements
