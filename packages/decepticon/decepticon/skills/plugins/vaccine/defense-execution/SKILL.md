---
name: defense-execution
description: >
  Deploy a compensating control for a planned Mitigation and record the action
  in the engagement knowledge graph as a DefenseAction node.
allowed-tools:
  - apply_defense
  - kg_query
  - kg_neighbors
metadata:
  version: "1.0.0"
  role: vaccine
  bundle: standard
  parent: vaccine
  priority: 20
---

# Defense Execution — Sub-Skill

You deploy compensating controls for planned Mitigations and record each
action in the knowledge graph.

## Inputs

- **mitigation_id** (required): ID of the Mitigation node (from a
  remediation brief).
- **finding_id** (required): ID of the Finding being addressed.
- **action_type** (required): category of the defence — one of:
  - `firewall_rule` — network-level ACL, WAF rule, or iptables entry.
  - `config_change` — service/OS configuration hardening.
  - `detection_rule` — Sigma, YARA, or Suricata rule deployment.
  - `code_patch` — application-level code fix.
  - `other` — any control not covered above.
- **description** (required): human-readable description of the control.
- **configuration** (optional): raw rule body, config diff, or patch content.

## Pre-Flight Checks

Before deploying, validate:

1. The `mitigation_id` exists in the KG and has `status` in
   (`planned`, `deployed`).  If `status == "verified"`, the Mitigation is
   already proven — skip and report.
2. The `finding_id` exists and does not have `vaccine_status == "mitigated"`.
   If already mitigated, skip and report.
3. The `action_type` is a recognised value.  Reject unknown types.

## Execution Steps

1. **Validate** — Run pre-flight checks above.
2. **Deploy** — Call `apply_defense` with all parameters.  The tool creates a
   `DefenseAction` node linked to the Finding and Mitigation.
3. **Confirm** — Query the KG to verify the `DefenseAction` node was created
   and edges are correct.
4. **Report** — Return the `defense_action_id` and deployment confirmation.

## Output Contract

```json
{
  "defense_action_id": "defense-action-abc123",
  "mitigation_id": "mitigation-def456",
  "finding_id": "finding-ghi789",
  "action_type": "firewall_rule",
  "status": "deployed",
  "note": "ACL blocking inbound traffic on port 8443 from untrusted zones."
}
```

## Error Handling

- If the KG write fails, retry once.  On second failure, report the error
  with the raw exception message.
- If pre-flight checks fail, return a structured error with the specific
  check that failed and the current node state.

## Constraints

- Do NOT verify the defence.  Verification is handled by `verify-defense`.
- Do NOT modify or delete existing DefenseAction nodes.  Each deployment
  creates a new action node; superseded actions remain in the graph for
  auditability.
- Do NOT deploy controls outside the engagement sandbox boundary.
