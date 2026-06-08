---
name: pretext-engineering
description: >
  Design a credible phishing pretext and target shortlist from OSINT before any
  campaign is built — sender persona, scenario, timing, and the minimal target set.
metadata:
  subdomain: phishing
  when_to_use: "pretext, lure design, target shortlist, phishing scenario, osint for phishing, sender persona, spearphishing"
  mitre_attack:
    - T1598
    - T1598.002
    - T1598.003
    - T1585
  tags:
    - phishing
    - social-engineering
    - osint
    - pretext
---

# Pretext Engineering

The pretext is the campaign. A technically perfect evilginx2 proxy
behind an implausible story converts nobody and burns the engagement.
Design the story first, from real OSINT, then pick the smallest target
set that proves the objective.

## Inputs

- `plan/roe.json`: permitted pretext classes, out-of-scope users,
  VIP exclusions, `data_handling`.
- OSINT handoff (from the OsintOperator): employee list, org chart,
  email format, tech stack, current events (mergers, migrations).

## Build the pretext

1. **Pick a scenario the target already expects.** The best pretexts
   ride a real process: an in-progress SSO/MFA migration, a benefits
   open-enrollment window, a shared-document notification from a tool
   the org actually uses (read the tech stack from OSINT).
2. **Choose the sender persona.** Internal IT, a known SaaS vendor, or
   a real internal sender — but ONLY impersonate an internal employee
   if `plan/roe.json:permitted_actions` allows it.
3. **Define the call to action.** One click → the lure domain. Keep it
   single-step.
4. **Set timing.** Match send-time to the scenario (e.g. Monday
   09:00 for an "IT maintenance this week" lure) and the engagement
   `opsec_level` send rate.

## Target shortlist

- Start with 1–3 users for the first wave (validate deliverability +
  detection window before scaling).
- EXCLUDE anyone in `out_of_scope` or flagged `vip: true`.
- Prefer roles that satisfy the objective (e.g. for cloud access,
  target an engineer with console access, not reception).

## Forbidden lure patterns

- NEVER promise monetary reward or threaten immediate termination —
  these spike helpdesk volume and break blue-team coverage.
- NEVER use a brand that could be confused with a different customer.

## Output

Write `plan/phisher/pretext.md` (scenario, persona, CTA, send window,
target shortlist with rationale) and create the target `User` nodes in
the knowledge graph. This file is the input to `gophish-campaign` /
`evilginx2-proxy` and to the mandatory `lure-deconfliction` handshake.
