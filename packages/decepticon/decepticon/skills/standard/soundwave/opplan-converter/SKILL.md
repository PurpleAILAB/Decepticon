---
name: opplan-converter
description: "Convert engagement documents into machine-readable OPPLAN for the ralph loop — objective decomposition, acceptance criteria, MITRE mapping, priority ordering."
allowed-tools: Read Write Edit
metadata:
  subdomain: planning
  when_to_use: "create OPPLAN, generate objectives, set up the loop, convert plan to tasks, make it runnable"
  tags: opplan, objectives, ralph-loop, automation
  upstream_ref: "Soundwave OPPLAN converter — engagement document → machine-readable objectives for the ralph loop"
---

# OPPLAN Converter — CONOPS to Ralph Loop Format

The OPPLAN is the **direct analogue of ralph's prd.json** — it's the file the autonomous loop reads each iteration to decide what to do next. Each objective must be completable by one agent in one context window.

## When to Use

- After both `plan/roe.json` and `plan/conops.json` exist
- User wants to convert planning docs into executable tasks
- Starting the autonomous red team loop

## Prerequisites

Read both `plan/roe.json` and `plan/conops.json` first. The RoE constrains what's allowed; the CONOPS defines the kill chain and threat profile.

See `../references/schema-quick-reference.md` for the `OPPLAN` and `Objective` schema fields, valid status values, and enum types.

## Workflow

### Step 1: Extract Kill Chain from CONOPS

Read the CONOPS kill chain phases. Only create objectives for authorized phases.

### Step 2: Decompose into Objectives

Each objective must follow the **one context window** rule — if an agent can't complete it in a single session, it's too big. Split it.

See `references/objective-templates.md` for recon-phase templates and `references/objective-rules.md` for the complete decomposition rules.

**ID Convention:** `OBJ-{NUMBER}` (auto-generated as OBJ-001, OBJ-002, ...)

**Phase → Sub-Agent Routing:**

| Phase | Sub-Agent | MITRE Tactics |
|-------|-----------|---------------|
| recon | recon | TA0043 Reconnaissance |
| initial-access | exploit | TA0001 Initial Access, TA0002 Execution |
| post-exploit | postexploit | TA0003-TA0009 (Persistence thru Collection) |
| c2 | postexploit | TA0011 Command and Control |
| exfiltration | postexploit | TA0010 Exfiltration |

### Step 3: Write Acceptance Criteria

Every objective MUST have three mandatory criteria types:

1. **Scope check** — "All targets verified against plan/roe.json in-scope list"
2. **OPSEC check** — At least one OPSEC-related criterion (rate limit, timing, etc.)
3. **Output persistence** — "Results saved to <engagement>/recon/..." (or exploit/, post-exploit/) with specific file path

Beyond these, add criteria specific to what the objective accomplishes. Every criterion must be mechanically verifiable — no vague statements like "good coverage."

### Step 4: Assign Metadata

For each objective:
- **priority** — Sequential, respects kill chain ordering and dependencies
- **mitre** — List of MITRE ATT&CK technique IDs (e.g. ["T1190", "T1059.004"])
- **opsec** — OPSEC level: loud, standard, careful, quiet, silent
- **opsec_notes** — Specific OPSEC constraints for this objective
- **c2_tier** — C2 tier matching OPSEC level: interactive, short-haul, long-haul
- **concessions** — Pre-authorized assists if objective is blocked (TIBER/CORIE concept)
- **blocked_by** — Objective IDs that must complete first

### Step 5: Generate OPPLAN

Use `add_objective` (one at a time, set `engagement_name` and `threat_profile` on first call) → `list_objectives` to review → present for user approval. No mode switching needed — OPPLAN tools are always available.

### Step 6: Validate

See `references/objective-rules.md` validation checklist before finalizing.

## Output

Present a summary table showing all objectives with phase, priority, title, OPSEC level, and MITRE mapping. Wait for user approval before starting execution.
