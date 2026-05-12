---
name: roe-template
description: "Rules of Engagement document creation — scope definition, prohibited/permitted actions, testing windows, escalation contacts, incident procedures."
allowed-tools: Read Write Edit
metadata:
  subdomain: planning
  when_to_use: "create RoE, define scope, engagement boundaries, start new engagement"
  tags: roe, scope, engagement, authorization, legal
  mitre_attack: []
---

# Rules of Engagement (RoE) Generator

The RoE is the **legally binding** foundation of every red team engagement. All other documents build on it.

## When to Use

- Starting a new engagement
- User says "create RoE", "define scope", "set boundaries"
- Before any other planning document can be created

## Workflow

### Step 1: Interview the User

Ask these questions in **two rounds** (batch related questions to minimize back-and-forth):

**Round 1 — Identity & Scope:**
1. Engagement name and client organization
2. Engagement type: `external` / `internal` / `hybrid` / `assumed-breach` / `physical`
3. Start date, end date, testing window (with timezone)
4. In-scope targets — use the appropriate `type` for each:
   - `domain` — hostname or wildcard (e.g. `*.example.com`)
   - `ip-range` — CIDR notation (e.g. `10.0.0.0/24`)
   - `cloud-resource` — AWS/GCP/Azure resource identifier
   - `source_code` — **local filesystem path** (e.g. `/home/user/myapp`). The launcher automatically copies this into the sandbox at `/workspace/src` before the analyst starts — no manual `docker cp` needed.
   - `live_service` — running HTTP/TCP endpoint (e.g. `http://host.docker.internal:8080`)
   - `git-repo` — git repository URL
   - `file-upload` — uploaded binary or archive
5. Out-of-scope targets (explicit exclusions)

**Round 2 — Boundaries & Escalation:**
6. Additional prohibited actions beyond defaults
7. Special permitted actions (phishing, password spraying, etc.)
8. Escalation contacts (minimum 2: client + red team lead) — name, role, channel
9. Authorization reference (contract #, signed letter)

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
