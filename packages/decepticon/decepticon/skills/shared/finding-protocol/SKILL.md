---
name: finding-protocol
description: "Operational-tier finding template — minimal fields for sub-agent decision support. Heavyweight deliverable promotion lives in skills/decepticon/final-report."
allowed-tools: Read Write
metadata:
  subdomain: reporting
  when_to_use: "write finding, record finding, create finding, document vulnerability, FIND-, findings/, severity"
  tags: finding, protocol, template, severity, reporting, documentation, operational
  upstream_ref: "Operational-tier finding template — sub-agent decision support output, not an attack technique"
---

# Finding Protocol — Operational Tier

The operational tier captures the minimum information another agent (or
the orchestrator) needs to make a decision. It is not the report
deliverable — the deliverable is generated at engagement end by the
orchestrator from operational findings + attack-path narrative (see
`skills/decepticon/final-report/SKILL.md`).

## File Naming Convention

`findings/FIND-{NNN}.md`

The file name and the `id` field in YAML frontmatter (FIND-001,
FIND-002, ...) use the same canonical cross-reference. Determine the
next ID by counting existing files: `ls findings/*.md | wc -l`.

Do not create empty scaffold directories or placeholder files before
there is a real artifact to write.

## Operational Template

Every operational finding uses this minimal Markdown structure with
YAML frontmatter — required fields only:

```markdown
---
id: FIND-001
severity: critical
title: <one-line summary>
cwe: CWE-89               # optional at operational tier; REQUIRED at deliverable promotion
vrt: server-side-injection/sql-injection/blind   # optional Bugcrowd VRT path (category/sub-category/variant)
agent: recon | exploit | postexploit | analyst | ...
objective_id: OBJ-001
discovered_at: "2026-04-06T14:23:11Z"
evidence_pointer: findings/evidence/FIND-001_<slug>.txt
---

## Description
2-4 sentences: what the issue is and where.

## Evidence
- <pointer 1>: <one-line per pointer>
- <pointer 2>: <one-line per pointer>

## Next
next agent should: <action>
OR
blocking — <reason>
```

The `## Next` section is the decision-support hook — the orchestrator
reads it to choose the next dispatch.

## Severity Guide (operational, principle-only)

- **CRITICAL**: Immediate exploitation, data breach, full compromise
- **HIGH**: Known CVE, significant misconfiguration, privilege escalation
- **MEDIUM**: Information disclosure, weak configuration
- **LOW**: Hardening recommendation, informational
- **INFORMATIONAL**: Observation, no direct security impact

CVSS-numeric ranges live in deliverable tier (see final-report skill). When a
CVSS score is recorded, always store the **vector string** (CVSS v4.0, e.g.
`CVSS:4.0/AV:N/AC:L/...`) alongside the numeric score — the vector encodes the
version and makes the score reproducible/auditable (per FIRST CVSS v4.0). A
bare number is ambiguous between v3.1 and v4.0.

## Classification fields (CWE + VRT)

- `cwe` — the CWE identifier (e.g. `CWE-89`). Optional at operational tier
  (recon often cannot determine it; exploit usually can), **required** when the
  finding is promoted to the deliverable tier.
- `vrt` — Bugcrowd Vulnerability Rating Taxonomy path
  `category/sub-category/variant` (e.g. `server-side-injection/sql-injection/blind`).
  Optional but recommended; it carries a machine-readable cross-walk to CVSS/CWE
  and a P1–P5 priority, and keeps classifications interoperable with bug-bounty
  triage. See the VRT at github.com/bugcrowd/vulnerability-rating-taxonomy.

## After Creating a Finding

1. Save raw evidence to `findings/evidence/FIND-{NNN}_{description}.txt`
   only when it supports the finding.
2. Append a timeline entry to `timeline.jsonl` for the real finding event:
   `{"ts":"...","type":"finding","id":"FIND-001","severity":"critical","agent":"recon","objective":"OBJ-001"}`

## Rules

- One Markdown file per finding — do NOT bundle multiple vulnerabilities
- ALL agent documents use Markdown format — never write JSON as a deliverable document
- Do NOT create `findings.md`; each finding lives in its own `findings/FIND-{NNN}.md` file

## Promotion to Deliverable Tier

When the orchestrator runs the final-report skill at engagement end,
operational findings are promoted to deliverable-tier finding documents under
`report/` with the heavyweight schema (CVSS score + vector, CWE, VRT, MITRE,
affected_target, affected_component, confidence, phase, detected,
remediation_priority, plus full body sections). See
`skills/decepticon/final-report/SKILL.md` for the deliverable template.

**Two-tier naming — the key vs. the deliverable:**

- **Operational tier** (`findings/FIND-{NNN}.md`) keeps the *stable*
  `FIND-NNN` key for the whole engagement. Severity and title may change as the
  exploit confirms impact, but the filename never does — so every cross-
  reference (`shells.json` / `creds` `finding_id`, `attack-paths/PATH-NNN`
  `finding_ids`, `timeline.jsonl`, `evidence/FIND-NNN_*.txt`) stays intact.
- **Deliverable tier** (`report/<severity><NN>-<slug>.md`) is the terminal
  snapshot generated once at engagement end, when severity is final. It uses a
  human-readable, severity-sorted name — e.g. `report/critical01-struts-rce.md`,
  `report/high01-git-config-disclosure.md`. The `<NN>` is a per-severity
  counter (`critical01`, `critical02`, `high01`, …) so a plain `ls report/`
  lists findings worst-first. The frontmatter still carries `id: FIND-NNN`, so
  the readable deliverable remains traceable back to its operational finding and
  to the attack-path / shell / credential cross-references.
