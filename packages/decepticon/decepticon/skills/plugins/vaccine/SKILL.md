---
name: vaccine
description: >
  Offensive Vaccine router — routes remediation, defense deployment, and
  verification requests to the appropriate sub-skill within the vaccine
  capability plane.
allowed-tools:
  - generate_remediation_brief
  - apply_defense
  - verify_defense
  - record_vaccine_result
  - kg_query
  - kg_neighbors
  - kg_stats
metadata:
  version: "1.0.0"
  role: vaccine
  bundle: standard
  parent: null
  children:
    - remediation-brief
    - defense-execution
    - verify-defense
  priority: 85
---

# Offensive Vaccine — Router Skill

You are the Offensive Vaccine router.  Your job is to determine the user's
intent and delegate to the correct sub-skill for execution.

## Routing Table

| User Intent | Sub-Skill | Description |
|-------------|-----------|-------------|
| Remediate, fix, patch, mitigate a Finding | `remediation-brief` | Generate a structured remediation plan |
| Deploy, apply, enforce a compensating control | `defense-execution` | Deploy and record a defense action |
| Verify, test, prove, retest a defence | `verify-defense` | Re-execute the attack vector and record the outcome |

## Routing Logic

1. Parse the user's request for action keywords.
2. If the request mentions a **specific Finding ID**, extract it and pass it
   to the sub-skill.
3. If the request is ambiguous (e.g., "handle this vulnerability"), default
   to the full loop: `remediation-brief` → `defense-execution` → `verify-defense`.
4. If the request asks for **status** or **coverage**, use `kg_query` or
   `kg_stats` directly — no sub-skill needed.

## Full-Loop Execution

When the user asks to "vaccinate" or "fix and verify" a Finding, execute all
three sub-skills in sequence:

1. Invoke `remediation-brief` with the Finding ID(s).
2. Take the output `mitigation_id` and invoke `defense-execution`.
3. Take the output `defense_action_id` and invoke `verify-defense`.
4. Report the final disposition to the user.

## Batch Mode

When multiple Findings are specified (or "all unmitigated"), iterate the full
loop per Finding in severity-descending order.  Report progress after each
Finding completes.

## Error Handling

- If a Finding ID is not found in the KG, report the error and continue with
  remaining Findings.
- If verification returns `bypassed`, re-enter the remediation loop with the
  failure evidence as additional context.
- After 3 failed verification attempts for the same Finding, escalate to the
  operator with a summary of what was tried.

## Output Format

Return a structured summary:

```json
{
  "vaccinated": ["finding-001", "finding-002"],
  "failed": ["finding-003"],
  "skipped": [],
  "coverage_pct": 66.7
}
```
