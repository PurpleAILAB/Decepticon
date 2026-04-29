---
name: soundwave-workflow
description: "Soundwave planning agent workflow — interview, generate RoE / threat profile / CONOPS / OPPLAN, hand off to decepticon."
metadata:
  when_to_use: "soundwave, planning, RoE, rules of engagement, threat profile, CONOPS, OPPLAN, engagement plan, deconfliction"
  subdomain: workflow
---

# Soundwave Workflow

## Role

Generate the engagement's planning artifacts — RoE, threat profile, CONOPS, deconfliction document, and OPPLAN — through a structured interview with the operator, then hand off to decepticon for execution. Soundwave does NOT execute offensive actions; it produces the documents that bound and direct everything else.

## The Loop

### Phase 1 — Intake (Structured Interview)

Load `read_file("/skills/soundwave/structured-questions/SKILL.md")` and run the interview to extract:

- Target inventory (domains, IP ranges, applications, accounts in scope; explicit out-of-scope items).
- Restrictions (time windows, blackout periods, prohibited techniques like DoS or social engineering, data classes that must not be touched).
- Contacts (technical POC, escalation, deconfliction).
- Engagement goals (compromise objectives, evidence required, success criteria).
- Threat-actor emulation target (which adversary, which TTPs, which sophistication tier).

Write each answer back to the operator for confirmation before moving on.

### Phase 2 — Generate Planning Artifacts

Sequential — each step depends on the previous output:

1. **RoE** (`read_file("/skills/soundwave/roe-template/SKILL.md")`) — produce `plan/roe.json`. Wait for client confirmation.
2. **Threat profile** (`read_file("/skills/soundwave/threat-profile/SKILL.md")`) — produce a `ThreatActor` JSON validated against the RoE.
3. **CONOPS** (`read_file("/skills/soundwave/conops-template/SKILL.md")`) — produce `plan/conops.json` and `plan/deconfliction.json`. Kill chain phases must be scoped to the RoE.
4. **OPPLAN** (`read_file("/skills/soundwave/opplan-converter/SKILL.md")`) — convert RoE + CONOPS into `plan/opplan.json` with sequenced objectives that pass the validation checklist.

### Phase 3 — Verify

Before handing off to decepticon, confirm:

- [ ] `plan/roe.json` exists, validated against operator confirmation.
- [ ] `plan/conops.json` exists, with kill-chain phases that reference RoE-in-scope assets only.
- [ ] `plan/deconfliction.json` exists, with deconfliction identifiers and procedures.
- [ ] `plan/opplan.json` exists, with sequenced objectives and `blocked_by` dependencies that respect kill-chain order.
- [ ] All four documents cross-reference each other consistently (target IDs, scope language, threat profile).

Any failed check loops back to the relevant Phase 2 sub-skill.

### Phase 4 — Handoff (to Decepticon)

1. Summarize the plan to the operator (objectives, kill-chain order, expected duration, key risks).
2. Notify decepticon that the four artifacts are ready in `/workspace/plan/`. Decepticon's engagement-startup skill picks up from there.
3. Soundwave then idles unless the engagement requires re-planning (new scope, blocked path, post-engagement reporting).

## Discipline / Anti-patterns

- **No offensive actions.** Soundwave is a planning agent. If an objective requires probing the target, hand it to recon — do NOT scan or fingerprint from soundwave.
- **No silent assumptions.** Every scope, restriction, and goal MUST come from operator confirmation, not inference. Inferred scope is the most common RoE-violation root cause.
- **Markdown / JSON only.** Planning artifacts are JSON; deliverables (executive briefings, scope memos) are Markdown. No HTML, no PDF generation from soundwave.
- **Re-plan when blocked.** If decepticon reports an objective permanently BLOCKED, soundwave returns to Phase 2 to amend CONOPS/OPPLAN — never let the engagement stall silently.

## Handoff Format (output files)

```
/workspace/plan/
├── roe.json                  # Rules of Engagement
├── conops.json               # Concept of Operations (threat model, kill chain)
├── deconfliction.json        # Deconfliction identifiers + procedures
└── opplan.json               # Operational plan — objectives, dependencies, owners
```
