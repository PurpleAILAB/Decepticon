---
name: chain-ssrf-to-rce
description: Build and validate SSRF pivot chains toward metadata/infra control and final code execution impact.
---

# Chain: SSRF to RCE

## Canonical path
1. SSRF reaches metadata/internal control plane.
2. Extract credential/token or access internal admin API.
3. Use credential to deploy or execute payload.
4. Confirm code execution and business impact.

## Graph guidance
- Add `enables` edges for each pivot.
- Lower weights for direct pivots; higher for speculative pivots.
- Run `plan_attack_chains` and then `suggest_objectives_from_chains`.
