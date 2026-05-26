---
name: conops-template
description: "Concept of Operations document creation — executive summary, threat actor profiling, attack narrative, kill chain design, communication plan, deconfliction."
allowed-tools: Read Write Edit
metadata:
  subdomain: planning
  when_to_use: "create CONOPS, design operation, threat model, plan attack"
  tags: conops, kill-chain, threat-model, operation-design
  mitre_attack: []
---

# Concept of Operations (CONOPS) Generator

The CONOPS bridges the legal RoE and the tactical OPPLAN. It must be **readable by a CEO** while containing **enough detail for operators**.

## When to Use

- After `roe.json` exists
- User says "create CONOPS", "design the operation", "build threat model"
- Before OPPLAN can be generated

## Prerequisites

Read `roe.json` first — scope and boundaries constrain the CONOPS.

See `../references/schema-quick-reference.md` for the `CONOPS`, `ThreatActor`, `KillChainPhase`, and `DeconflictionPlan` schema fields.

## Workflow

### Step 1: Interview the User

**Round 1 — Threat Model:**
1. Which threat actor to emulate? (Use `threat-profile` skill for detailed profiling)
   - a) Opportunistic external attacker (low)
   - b) Targeted cybercriminal (medium)
   - c) APT / nation-state (high)
   - d) Insider threat
   - e) Custom — describe
2. What is the attacker's motivation? (financial, espionage, disruption, hacktivism)
3. What initial access vector would this actor use?

**Round 2 — Operations:**
4. Attack narrative — 2-3 sentence scenario description
5. Ultimate objectives — what does the attacker want to achieve?
6. Communication plan — how does the red team communicate internally and with client?
7. Deconfliction method — how to distinguish red team from real attacks?
8. Success criteria — what constitutes engagement success?

### Step 2: Design Kill Chain

Based on RoE scope + threat profile, select applicable phases. See `references/kill-chain-templates.md`.

**Key rule**: Don't include phases outside RoE scope. Recon-only engagement → only `recon` phase.

### Step 3: Generate Documents

1. `conops.json` — matching `CONOPS` schema
2. `deconfliction.json` — matching `DeconflictionPlan` schema

### Step 4: Validate

- Executive summary contains no jargon or tool names
- Kill chain phases align with RoE scope
- All MITRE ATT&CK technique IDs are valid
- Timeline has concrete date ranges
- At least 2 success criteria defined

## Generation Rules

1. **Executive summary = non-technical** — no tool names, no jargon
2. **Threat actor TTPs must reference MITRE ATT&CK IDs**
3. **Kill chain scoped to RoE** — no exploitation phase in recon-only engagement
4. **Timeline uses absolute dates** — never relative
5. **Communication plan specifies frequency + channel**
