---
name: chain-idor-to-priv-esc
description: Build chains where IDOR enables privilege escalation and high-impact control-plane actions.
---

# Chain: IDOR to Privilege Escalation

## Canonical path
1. IDOR modifies another user's sensitive object.
2. Escalate role/permissions or steal recovery token.
3. Perform admin-level action and show impact.

## Validation
Demonstrate before/after authorization state and downstream privileged action evidence.
