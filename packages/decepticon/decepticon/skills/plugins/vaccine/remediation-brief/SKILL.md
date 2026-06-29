---
name: remediation-brief
description: >
  Generate a structured remediation brief for one or more confirmed Findings.
  Produces a prioritised mitigation plan with root-cause analysis, fix options,
  compensating controls, and verification criteria.
allowed-tools:
  - generate_remediation_brief
  - kg_query
  - kg_neighbors
metadata:
  version: "1.0.0"
  role: vaccine
  bundle: standard
  parent: vaccine
  priority: 10
---

# Remediation Brief — Sub-Skill

You generate structured remediation briefs for confirmed Findings in the
engagement knowledge graph.

## Inputs

- **finding_id** (required): one or more Finding node IDs from the KG.
- **priority_override** (optional): override the default severity-based
  ordering with a custom priority list.

## Execution Steps

1. **Validate** — Confirm each `finding_id` exists in the KG.  If not found,
   report the error and skip that Finding.

2. **Enrich** — For each valid Finding, query the KG for linked context:
   - Technique(s) used (`-[:USES_TECHNIQUE]->`)
   - Target host(s) (`-[:ON_HOST]->`)
   - Target service(s) (`-[:ON_SERVICE]->`)
   - Existing Mitigations (`<-[:ADDRESSES]-` Mitigation nodes)

3. **Check for existing mitigations** — If a Mitigation node with
   `status == "verified"` already exists, skip the Finding and note it as
   already resolved.

4. **Generate** — Call `generate_remediation_brief` for each Finding.  The
   tool creates a `Mitigation` node with `status = "planned"` and returns a
   structured brief.

5. **Format** — Present the brief(s) to the caller in the following structure:

```json
{
  "briefs": [
    {
      "finding_id": "finding-abc123",
      "mitigation_id": "mitigation-def456",
      "severity": "critical",
      "root_cause": "Unauthenticated RCE via deserialization in /api/import",
      "fix_options": [...],
      "compensating_controls": [...],
      "verification_criteria": [...]
    }
  ],
  "skipped": [],
  "errors": []
}
```

## Prioritisation

When processing multiple Findings, order by:

1. **Severity** — critical > high > medium > low > informational.
2. **Exploitability** — Findings with a proven exploit chain rank higher.
3. **Blast radius** — Findings affecting more hosts or services rank higher.

## Constraints

- Do NOT deploy any defences.  This skill only *plans*; deployment is handled
  by `defense-execution`.
- Do NOT fabricate fix options.  Every recommendation must be grounded in the
  Finding's context (technique, host, service).
- If the Finding lacks sufficient context for a meaningful brief, say so
  explicitly rather than generating a generic response.

## Output Contract

The returned JSON must include:

- `briefs`: array of generated brief objects (one per Finding).
- `skipped`: array of Finding IDs skipped (already mitigated).
- `errors`: array of `{finding_id, reason}` for Findings that could not be
  processed.
