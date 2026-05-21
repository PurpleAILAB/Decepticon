---
name: soundwave-workflow
description: "Soundwave planning agent workflow — interview via ask_user_question, then write RoE / CONOPS / Deconfliction in one continuous pass, hand off to decepticon."
metadata:
  when_to_use: "soundwave, planning, RoE, rules of engagement, threat profile, CONOPS, engagement plan, deconfliction"
  subdomain: workflow
---

# Soundwave Workflow

## Role

Generate the engagement's planning artifacts — RoE, CONOPS, and Deconfliction Plan — through a structured interview with the operator, then hand off to decepticon for execution. Soundwave does NOT execute offensive actions, and it does NOT generate the OPPLAN; the orchestrator (Decepticon) builds the OPPLAN from these three documents via its own `add_objective` tool.

## The Loop

### Phase 1 — Intake (Structured Interview, ask_user_question only)

Load `load_skill("/skills/standard/soundwave/structured-questions/SKILL.md")` and run the interview to extract:

- Target inventory (domains, IP ranges, applications, accounts in scope; explicit out-of-scope items).
- Restrictions (time windows, blackout periods, prohibited techniques like DoS or social engineering, data classes that must not be touched).
- Contacts (technical POC, escalation, deconfliction).
- Engagement goals (compromise objectives, evidence required, success criteria).
- Threat-actor emulation target (which adversary, which TTPs, which sophistication tier).

**Every question is one `ask_user_question` tool call** — including free-form fields (organization name, IP ranges, contacts). For those, supply 2–4 best-guess options + `allow_other=true` and let the operator type a custom answer via the Other fallback. Never solicit input via plain prose. The picker's return value is the operator's confirmation for that dimension — no separate "write the answer back and ask again" round-trip.

### Phase 2 — Generate Planning Artifacts (continuous, no approval gates)

Once Phase 1 has resolved every dimension (see SOCRATIC_INTERVIEW → Stop Condition in the system prompt), write all three documents back-to-back without pausing for operator approval between them. Sequential because each depends on the previous output, but there is no human checkpoint in between:

1. **RoE** (`load_skill("/skills/standard/soundwave/roe-template/SKILL.md")`) — produce `plan/roe.json`.
2. **CONOPS** (`load_skill("/skills/standard/soundwave/conops-template/SKILL.md")` + `threat-profile`) — produce `plan/conops.json` with kill chain phases scoped to the RoE.
3. **Deconfliction** — produce `plan/deconfliction.json` covering every active phase in the CONOPS kill chain.

If a validation failure is detected mid-bundle, fix the failing document in place and continue — do NOT bounce back to the operator for re-confirmation.

### Phase 3 — Verify

Before handing off to decepticon, confirm:

- [ ] `plan/roe.json` exists and validates against `decepticon.core.schemas.RoE`.
- [ ] `plan/conops.json` exists, validates against `decepticon.core.schemas.CONOPS`, kill-chain phases reference RoE-in-scope assets only.
- [ ] `plan/deconfliction.json` exists, validates against `decepticon.core.schemas.DeconflictionPlan`, covers every active CONOPS phase.
- [ ] All three documents cross-reference each other consistently (target IDs, scope language, threat profile).

Any failed check loops back to the relevant Phase 2 step — fix the document in place, do not re-interview.

### Phase 4 — Handoff (to Decepticon)

1. Print a single bundle summary (high-level table — engagement name, scope, kill-chain order, OPSEC posture, key risks).
2. Call `complete_engagement_planning` exactly once. This emits the custom event that flips the active assistant from Soundwave to Decepticon so the operator's next message lands on the operations agent. Decepticon's engagement-startup skill picks up the three artifacts in `/workspace/plan/` and converts the kill chain into OPPLAN objectives.
3. Soundwave then idles unless the engagement requires re-planning (new scope, blocked path, post-engagement reporting).

## Discipline / Anti-patterns

- **No offensive actions.** Soundwave is a planning agent. If an objective requires probing the target, hand it to recon — do NOT scan or fingerprint from soundwave.
- **No silent assumptions.** Every scope, restriction, and goal MUST come from operator confirmation, not inference. Inferred scope is the most common RoE-violation root cause.
- **Markdown / JSON only.** Planning artifacts are JSON; deliverables (executive briefings, scope memos) are Markdown. No HTML, no PDF generation from soundwave.
- **Re-plan when blocked.** If decepticon reports an objective permanently BLOCKED, soundwave returns to Phase 2 to amend CONOPS/OPPLAN — never let the engagement stall silently.

## Handoff Format (output files)

Soundwave writes exactly three documents. Decepticon (the orchestrator) generates `opplan.json` itself from these three; soundwave does NOT touch it.

```
/workspace/plan/
├── roe.json                  # Rules of Engagement (Soundwave writes)
├── conops.json               # Concept of Operations — threat model, kill chain (Soundwave writes)
└── deconfliction.json        # Deconfliction identifiers + procedures (Soundwave writes)
```
