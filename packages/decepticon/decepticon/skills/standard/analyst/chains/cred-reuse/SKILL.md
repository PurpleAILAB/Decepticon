---
name: chain-credential-reuse
description: Build chains where leaked or weak credentials pivot across services to privileged access.
---

# Chain: Credential Reuse Pivot

## Canonical path
1. Obtain credential (leak, default, weak hash crack).
2. Reuse across adjacent services.
3. Escalate privileges and reach crown jewel.

## Graph guidance
- Represent creds as `credential` nodes.
- Use `auth_as` and `grants` edges to model blast radius.
