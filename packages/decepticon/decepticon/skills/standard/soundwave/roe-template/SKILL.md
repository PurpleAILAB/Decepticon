---
name: roe-template
description: "Rules of Engagement document creation — scope definition, prohibited/permitted actions, testing windows, escalation contacts, incident procedures."
allowed-tools: Read Write Edit
metadata:
  subdomain: planning
  when_to_use: "create RoE, define scope, engagement boundaries, start new engagement"
  tags: roe, scope, engagement, authorization, legal
  upstream_ref: "Soundwave Rules of Engagement template — scope / window / escalation / incident procedures"
---

# Rules of Engagement (RoE) Generator

The RoE is the **legally binding** foundation of every red team engagement. All other documents build on it.

## When to Use

- Starting a new engagement
- User says "create RoE", "define scope", "set boundaries"
- Before any other planning document can be created

## Workflow

### Step 1: Interview the User

Drive each dimension through one `ask_user_question` call (per CRITICAL_RULES #8 — every operator-facing question goes through the tool). Cover these roughly in order, never bundling multiple questions in one turn:

**Identity & Scope**
1. Engagement name (free-form, `allow_other=true` with sensible guesses)
2. Client organization (free-form, `allow_other=true`)
3. Engagement type — single-select: `external` / `internal` / `hybrid` / `assumed-breach` / `physical`
4. Start date / end date / testing window with timezone (free-form, `allow_other=true` — suggest defaults like "Mon-Fri 09:00-18:00 client TZ")
5. In-scope targets (free-form, `allow_other=true` — domains, IP ranges, cloud resources, applications)
6. Out-of-scope targets (free-form, `allow_other=true`)

**Boundaries & Escalation**
7. Additional prohibited actions beyond schema defaults (multi-select with sensible options + `allow_other=true`)
8. Special permitted actions — phishing, password spraying, raw-socket scans (multi-select)
9. Escalation contacts — minimum 2 (client + red team lead). One ask per contact slot covering name, role, channel
10. Authorization reference / contract # (free-form, `allow_other=true`)

### Step 2: Generate roe.json

Use the `RoE` schema from `decepticon.core.schemas`. Write to the engagement directory.

See `references/roe-example.json` for a complete example and `../references/schema-quick-reference.md` for all required fields and valid values.

### Step 3: Validate

Run through the checklist in `references/validation-checklist.md` before presenting to user.

## Generation Rules

1. **Always include default prohibited actions** — DoS, unauthorized social engineering, unauthorized physical access, real data exfiltration, production data modification
2. **Scope must be specific** — CIDR notation for IPs, wildcard notation for domains
3. **Testing window must include timezone**
4. **At least 2 escalation contacts** required
5. **Authorization reference must not be empty**

## Output

Write `roe.json` to the engagement directory, then present a human-readable summary to the user for confirmation.
