---
name: idor
description: Hunt Insecure Direct Object Reference (CWE-639) — missing authorization checks on object IDs. Covers horizontal vs vertical privilege escalation, UUID vs integer guessing, and GraphQL introspection-driven IDOR discovery.
---

# IDOR Hunting Playbook

IDOR is the #1 source of bug bounty payouts because it's simple,
ubiquitous, and scanners can't find it (authorization is business
logic). Every endpoint that takes an object ID is a candidate.

## 1. Sources

- URL path segments: `/api/users/123/invoices/456`
- Query string: `?user_id=123`
- JSON body fields: `{"orderId": 123}`
- Headers used as auth scope: `X-Tenant-ID`, `X-Customer-Id`
- JWT claims that downstream handlers *trust*: `sub`, `tenant`, `role`
- WebSocket subscription filters
- GraphQL arguments (`user(id: 123)`)

## 2. Audit workflow

### Step 1 — enumerate object-handling endpoints
```bash
# REST
grep -rE '@(Get|Post|Put|Delete|Patch)Mapping.*\{[a-zA-Z]+Id\}' /workspace/src   # Spring
grep -rE 'router\.(get|post|put|delete)\([^)]*:id' /workspace/src                # Express
grep -rE '@app\.route\([^)]*<[a-z]+:' /workspace/src                             # Flask
grep -rE 'resources?\s+:[a-z]+' /workspace/src                                   # Rails

# GraphQL
grep -rE 'type Query|type Mutation' /workspace/src
grep -rE '\w+\(id: ID' /workspace/src
```

### Step 2 — for each endpoint, answer three questions
1. **Does it check who the caller is?** (auth middleware / decorator)
2. **Does it check whether the object belongs to the caller?**
   (ownership check / tenant filter in the query)
3. **Does it check whether the caller's role permits the action?**
   (RBAC / policy engine)

A "no" to question 2 = horizontal IDOR (read/write other users' data).
A "no" to question 3 = vertical IDOR (regular user → admin action).

### Step 3 — ownership-check grep patterns
```bash
# Django: should have .filter(user=request.user) on the queryset
grep -rE 'Model\.objects\.get\(pk=' /workspace/src | grep -v 'user=request\.user'

# Rails: should have current_user.posts.find(params[:id])
grep -rE 'Post\.find\(params\[:id\]\)' /workspace/src

# Spring: should have @PreAuthorize("#id == principal.id")
grep -rE 'findById\(id\)' /workspace/src | xargs -I{} grep -L '@PreAuthorize\|@PostAuthorize'
```

## 3. High-yield patterns

### GraphQL IDOR via introspection
```bash
curl -X POST https://target.com/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ __schema { types { name fields { name args { name type { name } } } } } }"}'
```
Any query field that takes an `id` arg and lacks a custom directive
(`@auth(requires: OWNER)`) is a candidate. Mutations are even higher
value — they often forget ownership checks.

### JWT claim trust
If the handler pulls `user_id` from `request.user.id` but also accepts
a `user_id` query param as override for "admin features", check whether
the override path enforces the admin claim. Frequently broken.

### Mass assignment via hidden fields
```python
User.objects.create(**request.POST.dict())
# allows POST'ing is_staff=true
```

## 4. PoC workflow

Two-account diff:
1. Create account A, note `sessionA` cookie and `objectA` ID.
2. Create account B, note `sessionB` cookie and `objectB` ID.
3. `curl -b sessionA /api/objects/<objectB>` — should 403.
4. If it returns 200 with objectB data → confirmed IDOR.

For vertical escalation:
1. Normal user cookie `sessionU`.
2. Call admin endpoint: `curl -b sessionU -X POST /api/admin/users/<victim>/role -d '{"role":"admin"}'`.
3. Watch the response code + subsequent `GET /api/users/<victim>`.

## 5. UUID vs integer

Sequential integer IDs make IDOR trivial. UUIDv4 makes it harder *but*:
- UUIDs leak in logs, emails, public URLs, support tickets
- Many apps use UUIDv1 (time-based) which is partially predictable
- Enumeration through a listing endpoint still works
- Some APIs accept both UUID and numeric ID (dual primary key)

Always test UUID endpoints — the "it's a UUID so it's safe" assumption
is one of the richest hunting grounds.

## 6. Success signals

- HTTP 200 where you expected 403/404
- Response body contains PII/data belonging to the other account
- Role field changed on victim account
- Subsequent admin action now permitted for low-priv session

Negative control: same request with your own account's ID. Should
return 200 with identical shape. Anything that returns 404 for your own
account but 200 for someone else's is a confirmation signal.

## 7. Default CVSS

| Variant                              | Vector                                        | Score |
|--------------------------------------|------------------------------------------------|-------|
| Horizontal read (other user PII)     | AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N           | 6.5   |
| Horizontal write (modify other user) | AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N           | 8.1   |
| Vertical escalation to admin         | AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H           | 9.9   |
| Unauth → any user profile            | AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N           | 7.5   |

## 8. Chain promotion

IDOR is a classic chain *starter*:
- IDOR → other user's password reset token → account takeover
- IDOR → admin role grant → every other admin-only vuln unlocked
- IDOR → internal API key → SSRF pivots

Weight 0.5 for authenticated IDOR, 0.3 for unauth.
