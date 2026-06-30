---
name: reverser-ransomware-analysis
description: "Ransomware family identification and analysis — encryption scheme identification, key recovery techniques, ransom note parsing, shadow copy/recovery inhibition analysis, decryptor availability check, and IOC extraction for common ransomware families."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "ransomware encrypted files ransom note decrypt recovery key lockbit revil conti blackcat alphv encryption crypto aes rsa chacha payment bitcoin"
  subdomain: reverser
  tags: "ransomware, encryption, decryptor, key recovery, incident response"
  mitre_attack: "T1486, T1490, T1489"
---

# Ransomware Analysis

Identify ransomware families, analyze encryption implementations, attempt key recovery, and extract IOCs for threat intelligence and incident response.

## Quick Reference

```bash
# Identify ransomware family from ransom note
# Upload to: id-ransomware.malwarehunterteam.com
# Or match locally:
strings ransom_note.txt | head -20

# Check encrypted file extension
ls -la /path/to/encrypted/ | head -20
# Common: .lockbit, .revil, .conti, .blackcat, .encrypted, .crypt

# Check for shadow copy deletion (recovery inhibition)
strings <TARGET> | grep -iE 'vssadmin|wmic.*shadowcopy|bcdedit|wbadmin'

# Entropy analysis on encrypted files
python3 -c "
import math
data=open('encrypted_file','rb').read()
c=[data.count(bytes([b])) for b in range(256)]
t=len(data)
e=-sum((x/t)*math.log2(x/t) for x in c if x)
print(f'Entropy: {e:.3f}/8 — {\"fully encrypted\" if e > 7.9 else \"partial/header encryption\" if e > 7.0 else \"not encrypted\"}')"

# Check Emsisoft/NoMoreRansom for free decryptors
# https://www.nomoreransom.org/en/decryption-tools.html
# https://www.emsisoft.com/en/ransomware-decryption/
```

## MITRE ATT&CK Mapping

| Technique | ID | How It Appears |
|---|---|---|
| Data Encrypted for Impact | T1486 | File encryption using AES/ChaCha20 + RSA key wrap |
| Inhibit System Recovery | T1490 | vssadmin delete shadows, bcdedit, wbadmin delete catalog |
| Service Stop | T1489 | Stopping SQL, Exchange, backup services before encryption |
| System Shutdown/Reboot | T1529 | Forced reboot after encryption; bootlocker ransomware |
| Data Destruction | T1485 | Wiper variants masquerading as ransomware |
| Exfiltration Over C2 | T1041 | Double extortion: data exfil before encryption |
| Defacement: Internal | T1491.001 | Desktop wallpaper change to ransom note |

## 1. Family Identification

Determine which ransomware family you're dealing with.

```bash
# Method 1: Ransom note analysis
cat ransom_note.txt
# Key identifiers:
# - Tor .onion URL → payment portal (extract for IOC)
# - Bitcoin/Monero wallet address
# - Unique victim ID / personal key
# - File extension mentioned in note

# Method 2: Encrypted file extension mapping
# .lockbit → LockBit 2.0/3.0
# .revil / .sodinokibi → REvil/Sodinokibi
# .CONTI → Conti
# .blackcat / random 6-7 char → BlackCat/ALPHV
# .royal → Royal
# .akira → Akira
# .play → Play
# .8base → 8Base (Phobos variant)
# .<random base64> → often Phobos family

# Method 3: ID Ransomware (web-based)
# Upload: ransom note + encrypted file sample
# https://id-ransomware.malwarehunterteam.com/

# Method 4: Binary analysis
strings <TARGET> | grep -iE 'lockbit\|revil\|conti\|blackcat\|phobos\|dharma\|stop\|djvu'
yara -r /opt/yara-rules/ransomware/ <TARGET>

# Method 5: Mutex / named pipe identification
strings <TARGET> | grep -iE 'Global\\|mutex\|pipe'
# Known mutexes: "Global\LockBit" → LockBit
```

## 2. Encryption Scheme Analysis

Reverse the crypto implementation to assess recoverability.

```bash
# Identify crypto libraries / APIs used
strings <TARGET> | grep -iE 'CryptEncrypt\|CryptGenKey\|CryptImportKey\|CryptAcquireContext'
strings <TARGET> | grep -iE 'AES\|RSA\|ChaCha\|Salsa\|Blowfish\|RC4\|ECDH\|Curve25519'
strings <TARGET> | grep -iE 'BCrypt\|NCrypt\|OpenSSL\|mbedtls\|sodium\|libcrypto'

# Common ransomware crypto patterns:
# Pattern A: RSA-2048 master key + AES-256-CBC per file (LockBit, Conti)
# Pattern B: Curve25519 + XSalsa20 (BlackCat/ALPHV — Rust-based)
# Pattern C: RSA-2048 + ChaCha20 per file (REvil, Hive)
# Pattern D: Hardcoded AES key (weak — decryptable!) (older Dharma, STOP/Djvu offline)

# Check import table for crypto APIs
python3 << 'EOF'
import pefile
pe = pefile.PE("<TARGET>")
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll = entry.dll.decode()
    for imp in entry.imports:
        name = imp.name.decode() if imp.name else f"ord_{imp.ordinal}"
        if any(k in name.lower() for k in ['crypt', 'rsa', 'aes', 'key', 'encrypt', 'hash', 'rand']):
            print(f"  {dll}: {name}")
EOF

# Analyze encrypted file structure
python3 << 'EOF'
import struct
with open("encrypted_file.lockbit", "rb") as f:
    # Many ransomware families append metadata to encrypted files
    f.seek(-256, 2)  # Read last 256 bytes
    trailer = f.read()
    print("Trailer hex:", trailer.hex())
    # Look for:
    # - Encrypted AES key (RSA-encrypted, typically 128/256 bytes)
    # - Original file size
    # - IV / nonce
    # - File marker / magic bytes

    # Check file header
    f.seek(0)
    header = f.read(64)
    print("Header hex:", header.hex())
    # Full-file encryption: high entropy from byte 0
    # Partial encryption: original header partially intact
EOF
```

## 3. Key Recovery Techniques

```bash
# Technique 1: Weak/Hardcoded Key (STOP/Djvu offline key, older variants)
# If ransomware uses CryptGenRandom but falls back on failure:
strings <TARGET> | grep -c "CryptGenRandom"
# If absent → may use deterministic key derivation (time-based, PID-based)

# Technique 2: Memory forensics — extract key from process memory
vol3 -f memory.raw windows.memmap --pid <RANSOMWARE_PID> --dump
# Search dump for AES key schedule patterns
python3 << 'EOF'
import re
data = open("pid.<PID>.dmp", "rb").read()
# AES-256 key schedule: 240 bytes with specific expansion pattern
# Search for high-entropy 32-byte sequences near CryptoAPI structures
candidates = []
for i in range(len(data) - 32):
    block = data[i:i+32]
    # Quick entropy check
    unique = len(set(block))
    if unique > 28:  # High byte diversity suggests key material
        candidates.append((i, block.hex()))
print(f"Found {len(candidates)} candidates")
for off, h in candidates[:20]:
    print(f"  0x{off:08x}: {h}")
EOF

# Technique 3: Known-plaintext attack
# If you have the original unencrypted file AND the encrypted version:
python3 << 'EOF'
orig = open("original.docx", "rb").read()
enc = open("original.docx.encrypted", "rb").read()
# XOR to recover keystream (if XOR/stream cipher was used)
keystream = bytes(a ^ b for a, b in zip(orig, enc))
print("First 64 bytes of keystream:", keystream[:64].hex())
# If keystream repeats → short key XOR → trivially breakable
EOF

# Technique 4: Flawed PRNG / implementation bugs
# WannaCry: CryptGenRandom not called → primes recoverable from memory
# Some Dharma: PID + timestamp as seed → predictable key
# GandCrab v1: RSA key generation flaw → Bitdefender decryptor

# Technique 5: Check for existing decryptors
# NoMoreRansom project: nomoreransom.org
# Emsisoft: emsisoft.com/ransomware-decryption
# Kaspersky: noransom.kaspersky.com
# Avast: avast.com/ransomware-decryption-tools
```

## 4. Recovery Inhibition Analysis

```bash
# Shadow copy deletion
strings <TARGET> | grep -iE 'vssadmin\s+delete\|shadows\s*/all'
strings <TARGET> | grep -iE 'wmic\s+shadowcopy\s+delete'
strings <TARGET> | grep -iE 'Get-WmiObject.*ShadowCopy.*Delete'

# Boot recovery disabling
strings <TARGET> | grep -iE 'bcdedit.*recoveryenabled.*no'
strings <TARGET> | grep -iE 'bcdedit.*bootstatuspolicy.*ignoreallfailures'

# Backup catalog deletion
strings <TARGET> | grep -iE 'wbadmin\s+delete\s+catalog'
strings <TARGET> | grep -iE 'delete\s+systemstatebackup'

# Service stopping (databases, backups, AV)
strings <TARGET> | grep -iE 'net\s+stop\|sc\s+stop\|taskkill\|Stop-Service'
# Common targets: MSSQLSERVER, SQLAgent, MySQL, oracle, veeam, backup, sophos, defender

# Attempt shadow copy recovery (if deletion failed or was partial)
vssadmin list shadows
# If shadows exist → mount and recover files

# Check for Volume Shadow Copy remnants in raw disk
# Even after vssadmin delete, data may persist until overwritten
```

## 5. Ransom Note Parsing and IOC Extraction

```bash
# Extract IOCs from ransom note
python3 << 'EOF'
import re

with open("ransom_note.txt", "r", errors="ignore") as f:
    note = f.read()

# Extract Tor onion URLs
onions = re.findall(r'[a-z2-7]{16,56}\.onion', note)
print("Tor URLs:", onions)

# Extract Bitcoin addresses (P2PKH, P2SH, Bech32)
btc = re.findall(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b', note)
btc += re.findall(r'\bbc1[a-zA-HJ-NP-Z0-9]{25,90}\b', note)
print("BTC addresses:", btc)

# Extract Monero addresses
xmr = re.findall(r'\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b', note)
print("XMR addresses:", xmr)

# Extract email addresses
emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', note)
print("Emails:", emails)

# Extract victim/personal IDs
victim_ids = re.findall(r'(?:ID|key|token|code)\s*[:=]\s*([A-Za-z0-9+/=\-]{16,})', note, re.I)
print("Victim IDs:", victim_ids)
EOF

# Trace Bitcoin wallet for attribution
# blockchain.com/explorer or blockchair.com
# Check if wallet is tagged in ransomwhere.re database
```

## 6. Binary-Level Behavioral Analysis

```bash
# File enumeration logic
strings <TARGET> | grep -iE '\.doc\|\.xls\|\.pdf\|\.jpg\|\.png\|\.sql\|\.mdb\|\.zip'
# Ransomware typically targets specific file extensions and skips system files

# Exclusion list (files/dirs ransomware avoids to keep OS bootable)
strings <TARGET> | grep -iE 'windows\|system32\|boot\|ntldr\|bootmgr\|\.exe\|\.dll\|\.sys'
# Skipping these is characteristic of ransomware (vs wipers)

# Network enumeration (worm-like propagation)
strings <TARGET> | grep -iE 'NetShareEnum\|WNetOpenEnum\|GetAdaptersInfo\|IcmpSendEcho'
# SMB scanning → lateral movement before encryption

# Process/service termination commands
strings <TARGET> | grep -iE 'taskkill.*sql\|taskkill.*oracle\|taskkill.*backup'

# Privilege escalation
strings <TARGET> | grep -iE 'SeDebugPrivilege\|AdjustTokenPrivileges\|runas\|ShellExecute.*admin'

# Anti-analysis checks
strings <TARGET> | grep -iE 'IsDebuggerPresent\|CheckRemoteDebugger\|GetSystemDefaultLangID\|GetKeyboardLayout'
# Language check: many ransomware families skip CIS countries (Russian keyboard = exit)
```

## Tools & Resources

| Tool | Purpose | Install |
|---|---|---|
| ID Ransomware | Family identification from note/sample | id-ransomware.malwarehunterteam.com |
| CyberChef | Crypto analysis, encoding/decoding | gchq.github.io/CyberChef |
| Emsisoft Decryptors | Free decryption tools | emsisoft.com/ransomware-decryption |
| NoMoreRansom | Decryptor repository | nomoreransom.org |
| ransomwhe.re | Ransomware payment tracking | ransomwhe.re |
| Volatility 3 | Memory forensics for key recovery | github.com/volatilityfoundation/volatility3 |
| YARA | Ransomware family signatures | github.com/Yara-Rules/rules |
| vssadmin | Shadow copy management | Built into Windows |
| Raccine | Ransomware vaccine (VSS protection) | github.com/Neo23x0/Raccine |

## Detection Signatures

| Indicator | Description | Detection |
|---|---|---|
| Mass file rename with new extension | Bulk encryption in progress | Sysmon File Create (Event 11) burst |
| `vssadmin delete shadows /all /quiet` | Shadow copy deletion | Sysmon Event ID 1 + command line |
| `bcdedit /set recoveryenabled no` | Recovery disabling | Sysmon Event ID 1 |
| Ransom note dropped in every directory | Encryption complete signal | File create events for `README.txt`, `DECRYPT.txt` |
| High-entropy file writes | Active encryption | I/O monitoring: write entropy > 7.9 |
| Services stopped in rapid succession | Pre-encryption service kill | Windows Event Log 7036 burst |
| Network share enumeration | Lateral movement / spread | NetShareEnum API calls, SMB traffic |
| Mutex creation with known names | Family identification | Sysmon Event ID 17 |

## Error Handling & Edge Cases

| Issue | Resolution |
|---|---|
| Ransomware sample won't run (anti-VM) | Patch anti-analysis checks; use bare-metal analysis host |
| No ransom note found | Check alternate locations: Desktop, every drive root, C:\Users\Public |
| Encrypted file has zero additional bytes | Header-only encryption — may be partially recoverable |
| Wiper disguised as ransomware | Check if decryption key actually exists; analyze if key is generated but never saved |
| Double-encrypted (two families) | Decrypt in reverse order; identify families by extension stacking |
| Network-propagating variant | Isolate host immediately; analyze SMB/RDP lateral movement code |
| Key deleted from memory | Cold boot attack; check pagefile.sys, hiberfil.sys for key remnants |

## Decision Gate

```
IF ransom note present:
  → Upload to ID Ransomware for family identification
  → Check NoMoreRansom / Emsisoft for free decryptor
  → Extract IOCs (onion URLs, BTC wallets, emails)
  → If decryptor exists → decrypt and recover
IF no decryptor available:
  → Analyze encryption implementation in binary
  → Check for crypto weaknesses (hardcoded key, weak PRNG, implementation bugs)
  → Attempt memory forensics for key material
  → Check for intact shadow copies / backup catalog
IF wiper suspected (no real key):
  → Document as destructive attack, not ransomware
  → Focus on IOC extraction and attribution
  → File recovery via disk carving (PhotoRec, foremost)
```
