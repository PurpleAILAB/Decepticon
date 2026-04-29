---
name: web-cookie-audit
description: "Cookie-conditional sink discovery — bisect required cookies per sink, session-write timeline for race-condition challenges."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "cookie audit, session cookies, sink preconditions, gating cookies, session mutation, session-write timeline, race-condition recon, TOCTOU recon"
  tags: cookie-audit, session-mutation, gating
  mitre_attack: T1539
---

# Cookie-Conditional Sink Discovery

A "sink" (eval, deserialize, exec, template render) may behave differently — or not fire at all — depending on which session cookies are present. Recon MUST enumerate every cookie the app sets and re-test each candidate sink with and without each cookie before declaring the sink unreachable. Skipping this step is the most common cause of exploit handing back a false "blind sink" verdict.

## Procedure

1. Walk the app unauthenticated; record every `Set-Cookie` (name, attributes, source endpoint).
2. Authenticate (every auth tier: anon, low-priv user, high-priv user) and record the full cookie jar after each.
3. For each candidate sink (parameter, route, header, body field):
   - Probe with NO cookies.
   - Probe with FULL authenticated jar.
   - Bisect: drop one cookie at a time and re-probe. The cookie whose removal silences the sink is the gating cookie.
4. Document a "Sink preconditions" table in `recon_notes.md` and `SUMMARY.txt`:

| Sink | Endpoint | Method | Required cookies | Behavior w/o cookie | Behavior w/ cookie | Notes |
|------|----------|--------|------------------|--------------------|--------------------|-------|
| `bookmark_data` (deser) | `/bookmarks/import` | POST | `session=...; auth_tier=user` | 302 → /login | 200 + processed | gated by auth_tier |

4a. **Session mutation audit.** For every endpoint that READS session, trace which other endpoints WRITE to the SAME session key BEFORE the security verdict (login, password check, role lookup). This is the data race-condition exploit needs. Output a "Session-write timeline" table:

| Endpoint | Reads session keys | Writes session keys (pre-verdict) | Slow ops (bcrypt/DB/network) | Race window (ms) |
|----------|--------------------|-----------------------------------|------------------------------|------------------|
| `POST /login` | — | `user`, `auth_tier` (set BEFORE bcrypt) | bcrypt ~200ms | ~200 |
| `GET /admin_panel` | `user`, `auth_tier` | — | — | reads during the login bcrypt window |

If the challenge tag includes `race_condition`, `toctou`, `concurrent`, or `smuggling_desync` and recon hands off WITHOUT this table, exploit MUST flag the handoff back as "recon incomplete: session-write timeline missing".

5. In the handoff to exploit/postexploit, ALWAYS include a **Required session state** line:

```
Required session state: cookies=[session, auth_tier=user]; obtained via POST /login (creds: user@example.com / hunter2)
```

If recon hands off without this line, exploit is required to re-run cookie enumeration before concluding any sink is unreachable.
