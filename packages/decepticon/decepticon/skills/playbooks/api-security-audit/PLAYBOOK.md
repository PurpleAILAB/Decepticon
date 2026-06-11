---
name: api-security-audit
description: "End-to-end API surface audit: map endpoints, then test authZ (BOLA/IDOR/BFLA), parameter pollution, and SSRF."
metadata:
  phase: web-exploitation
  tags: [api, bola, idor, bfla, parameter-pollution, ssrf, authorization]
  steps:
    - skill: web-api-enumeration
      goal: "Map the full API surface — enumerate REST/GraphQL endpoints, pull Swagger/OpenAPI and GraphQL introspection schemas, and fuzz the parameter surface of every reachable endpoint."
      phase: reconnaissance
    - skill: web-auth-mapping
      goal: "Model the authentication and session layer — identify token type (JWT/opaque/cookie), roles, tenant boundaries, and which object identifiers flow through which endpoints."
      phase: reconnaissance
    - skill: idor
      goal: "Test broken object-level authorization (BOLA/IDOR): swap object identifiers across user/tenant boundaries on every parameterised endpoint discovered, and verify the server enforces ownership."
      phase: web-exploitation
    - skill: auth-bypass
      goal: "Test broken function-level authorization (BFLA) and auth bypass: replay privileged-only methods/paths as a low-privilege principal, and probe parameter pollution (duplicate params, type juggling, JSON/array smuggling) that subverts authZ checks."
      phase: web-exploitation
    - skill: ssrf
      goal: "Test server-side request forgery through API parameters that accept URLs, hostnames, or webhook callbacks, pivoting to internal services and cloud metadata where reachable."
      phase: web-exploitation
---

# API Security Audit

A structured, ordered workflow for auditing an HTTP/GraphQL API end-to-end.
It composes existing skills into one chain: first **map** the surface, then
**attack the authorization model** (the dominant API risk class per the OWASP
API Security Top 10), then test the request-forgery surface that API
parameters expose. Each step feeds the next — endpoints and object
identifiers found in mapping are the inputs to the authorization tests.

## 1. Surface mapping & introspection (`web-api-enumeration`)

Establish *what exists* before testing *what is broken*:

- Enumerate REST endpoints and API versions (`/api/v1`, `/api/v2`, ...).
- Pull machine-readable contracts: `swagger.json`, `openapi.json`, `/api-docs`.
- Detect GraphQL endpoints and run an introspection query
  (`{__schema{types{name fields{name}}}}`) to recover the full type graph.
- Fuzz the parameter surface of each endpoint (GET/POST/headers) so later
  authorization tests know every identifier the server reads.

Output: an endpoint inventory annotated with the object identifiers and
parameters each route accepts.

## 2. Authentication & object model mapping (`web-auth-mapping`)

Before authorization can be tested, the trust model must be known:

- Identify the auth mechanism (JWT, opaque bearer, session cookie, API key).
- Enumerate roles/scopes and tenant boundaries.
- Trace which object identifiers (`user_id`, `order_id`, `account`, GraphQL
  node IDs) flow through which endpoints, and which are server-authoritative
  vs. client-supplied.

Output: a map of `(endpoint, identifier) → expected owner/role`, the oracle
the authorization tests assert against.

## 3. Broken object-level authorization — BOLA / IDOR (`idor`)

The #1 API risk. For every parameterised endpoint from step 1:

- Swap object identifiers horizontally (another user's `id`) and vertically
  (another tenant's resource).
- Test sequential, UUID, and hashed identifiers alike — predictability is a
  severity multiplier, not a precondition.
- Confirm the server enforces ownership server-side rather than trusting a
  client-supplied identifier.

## 4. Broken function-level authorization & parameter pollution (`auth-bypass`)

- BFLA: replay admin/privileged methods and routes as a low-privilege
  principal (e.g. `DELETE /api/users/{id}`, `POST /api/admin/*`).
- HTTP parameter pollution: duplicate parameters, mix query/body sources,
  and use array/object type juggling (`role=user&role=admin`,
  `{"role":["user","admin"]}`) to subvert authorization or input validation.
- Mass assignment: inject privileged fields (`is_admin`, `role`, `verified`)
  the API binds without an allowlist.

## 5. Server-side request forgery via API parameters (`ssrf`)

- Identify parameters that accept URLs, hostnames, or webhook callbacks.
- Attempt to coerce the API into requesting internal services
  (`127.0.0.1`, `169.254.169.254`, internal hostnames) and cloud metadata
  endpoints, then pivot on any reachable internal surface.

## Reporting

Tie each finding back to the `(endpoint, identifier) → expected owner/role`
oracle from step 2 so impact is expressed in business terms (which tenant's
data, which privileged action) rather than raw HTTP responses.
