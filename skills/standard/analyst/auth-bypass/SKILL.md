---
name: auth-bypass
description: Hunt authentication/authorization bypass in route guards, role checks, tenant boundaries, and state-machine transitions.
---

# Auth Bypass Playbook

## Targets
- Endpoints with role-based access
- Admin-only routes
- Tenant-scoped resources
- Multi-step auth flows (MFA, password reset)

## Common failure patterns
- Missing middleware on one route variant
- Trusting client-controlled role/tenant fields
- TOCTOU between check and action
- Alternate API versions lacking guard checks

## Validation
- Positive: low-priv session performs high-priv action.
- Negative: same request with expected guard path should deny.
