---
name: ad-domain-dominance
description: "Run once a foothold lands inside an Active Directory domain with any authenticated context: ordered chain from graph-driven recon through credential access to domain-replication compromise. Triggers on: 'AD compromise', 'domain admin path', 'kerberoast then dcsync', 'BloodHound to DA', 'internal AD engagement'."
metadata:
  phase: active-directory
  steps:
    - bloodhound-query
    - kerberoasting
    - dcsync
---

# Playbook — AD Domain Dominance

The canonical internal-AD escalation spine: let the graph pick the
shortest path, harvest a service credential along it, then replicate
the domain's secrets. Every step is driven by what BloodHound shows,
not by guesswork.

## Steps

| # | Skill | Goal | Gate to next step |
|---|-------|------|-------------------|
| 1 | `bloodhound-query` | Collect and query the AD graph for shortest paths to high-value targets from the current principal. | A concrete attack path (and its first edge) is identified. |
| 2 | `kerberoasting` | Request and crack service-account tickets along the path to obtain a stronger credential. | A privileged credential is recovered, or the path's roastable SPNs are exhausted. |
| 3 | `dcsync` | Use replication rights on the recovered credential to pull domain secrets (krbtgt, admins). | Domain-level credential material obtained. |

## Decision gates

- **After step 1** — BloodHound dictates the technique, not this
  playbook. If the shortest path is ACL-based (GenericAll, AddMember),
  ESC-chain (ADCS), or coercion/relay, branch to the matching `ad/*`
  skill (`certipy-esc-chain`, `ntlm-relay`, `coercer`, `dcsync` direct)
  instead of forcing Kerberoasting. Steps 2–3 are the most common edge,
  not the only one.
- **After step 2** — if no SPN is roastable or crackable, return to the
  graph for the next path (AS-REP roasting, LAPS, delegation) rather
  than escalating blind.
- **After step 3** — krbtgt extraction is golden-ticket territory and a
  loud, high-impact action: gate it on explicit RoE approval. Hand off
  to `post-exploit` lateral-movement / persistence with the recovered
  material.

## OPSEC

Kerberoasting and DCSync are both detectable (TGS-REQ volume, DRSUAPI
replication from a non-DC). Pace requests, prefer targeted SPNs over
mass roasting, and source DCSync from an expected host where possible.
