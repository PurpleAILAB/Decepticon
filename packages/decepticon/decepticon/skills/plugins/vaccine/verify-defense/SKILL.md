---
name: verify-defense
description: >
  Re-execute the original attack vector against a defended target to verify
  that a deployed DefenseAction is effective.  Records a VerificationResult
  with disposition and evidence.
allowed-tools:
  - verify_defense
  - record_vaccine_result
  - kg_query
  - kg_neighbors
metadata:
  version: "1.0.0"
  role: vaccine
  bundle: standard
  parent: vaccine
  priority: 30
---

# Verify Defense — Sub-Skill

You verify that a deployed defence is effective by re-executing the original
attack vector and recording the outcome.

## Inputs

- **defense_action_id** (required): ID of the DefenseAction to verify.
- **finding_id** (required): ID of the original Finding.
- **attack_replay_command** (required): the exact command, tool invocation,
  or exploit script to replay.  This should match the original attack vector
  from the Finding's provenance chain.

## Execution Steps

1. **Pre-flight** — Confirm the `defense_action_id` exists in the KG with
   `status == "deployed"`.  Confirm the `finding_id` exists.

2. **Create verification node** — Call `verify_defense` with all parameters.
   This creates a `VerificationResult` node with `disposition = "pending"`.

3. **Execute replay** — The sandbox executor runs the
   `attack_replay_command`.  Collect stdout, stderr, and exit code as raw
   evidence.

4. **Determine disposition**:
   - **blocked** — the attack failed entirely (connection refused, access
     denied, detection alert fired, non-zero exit with defence-related
     error).
   - **bypassed** — the attack succeeded as before (same output, same
     access gained).
   - **partial** — the attack partially succeeded (reduced impact, delayed
     execution, some but not all objectives achieved).

5. **Record result** — Call `record_vaccine_result` with the
   `verification_id`, `finding_id`, determined `disposition`, and raw
   evidence string.

6. **Handle failure** — If disposition is `bypassed` or `partial`:
   - Extract the failure reason from the evidence.
   - Report back to the router skill with a recommendation to re-enter
     the remediation loop with the failure context.
   - Do NOT automatically retry — the router decides retry strategy.

## Output Contract

```json
{
  "verification_id": "verification-abc123",
  "defense_action_id": "defense-action-def456",
  "finding_id": "finding-ghi789",
  "disposition": "blocked",
  "evidence": "Connection refused: port 8443 filtered by ACL ...",
  "vaccine_status": "mitigated",
  "closed": true
}
```

## Disposition Criteria

| Disposition | Criteria | Finding Status |
|-------------|----------|----------------|
| `blocked` | Attack fails entirely; defence provably effective | `mitigated` |
| `bypassed` | Attack succeeds unchanged; defence ineffective | `unmitigated` |
| `partial` | Attack partially succeeds; defence needs refinement | `partially_mitigated` |

## Iteration Protocol

When the router re-invokes this skill after a failed verification:

1. The new attempt gets a fresh `VerificationResult` node.
2. The prior result remains in the graph for auditability.
3. The router should provide updated `attack_replay_command` if the defence
   changed the attack surface (e.g., different port, different endpoint).

## Constraints

- Do NOT deploy new defences.  Verification only tests what is already
  deployed.
- Do NOT modify the `DefenseAction` node.  If the defence needs changes,
  return to `defense-execution` for a new action.
- ALWAYS record evidence even if the disposition is obvious.  The evidence
  string is the proof chain.
- The attack replay MUST run inside the engagement sandbox.  Never execute
  attack commands outside the isolated environment.

## Safety

Attack replay is inherently dangerous.  This skill relies on:

1. Sandbox isolation inherited from the Red Cell's engagement environment.
2. Full auditability via the `attack_replay_command` recorded in the KG.
3. The agent's inability to craft new attack vectors — it only replays
   existing ones from the Finding's provenance chain.
