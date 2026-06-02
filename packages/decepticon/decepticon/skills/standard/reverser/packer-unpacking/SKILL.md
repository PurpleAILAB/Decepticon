---
name: packer-unpacking
description: Identify and unpack common binary packers — UPX, ASPack, Themida, VMProtect, MPRESS, PECompact, Enigma.
metadata:
  subdomain: reverse-engineering
  when_to_use: "packer unpack upx aspack themida vmprotect mpress pecompact enigma unpacking"
  mitre_attack:
    - T1027.002
---

# Packer Unpacking Playbook

Packers compress and/or obfuscate binaries to defeat static analysis.
The first job: identify which packer, then dispatch the right unpacker
(or manual unpacking strategy if no automated tool exists).

## 1. Detect packing
```bash
# Entropy quick-check (>7.0 across the binary = likely packed)
ent /tmp/sample
# or
python3 -c "
import sys, math
d = open('/tmp/sample','rb').read()
f = [0]*256
for b in d: f[b] += 1
h = -sum((c/len(d))*math.log2(c/len(d)) for c in f if c)
print(f'entropy={h:.3f}')
"

# Section-level entropy via radare2
r2 -qc "iSj" /tmp/sample | jq '.[] | "\(.name): \(.entropy)"'

# Tool-based detection
detect-it-easy /tmp/sample  # most reliable, GUI + CLI
diec /tmp/sample           # CLI for DIE
yara -r /opt/yara-rules/packers/ /tmp/sample
```

Decepticon helper:
```
bin_packer("/tmp/sample")
```

## 2. Common packer signatures

| Packer | Signature |
|---|---|
| UPX | `UPX!` magic at section header, sections named `UPX0`, `UPX1` |
| ASPack | `.aspack` section, jump after entry to packed code |
| Themida | `.themida` section, anti-debug, anti-VM heavy |
| VMProtect | `.vmp0`, `.vmp1` sections; obfuscated EP w/ virtualized handlers |
| MPRESS | `.MPRESS1`, `.MPRESS2` sections |
| PECompact | `pec1` section, encrypted sections |
| Enigma | `.enigma1`, `.enigma2` sections |
| Petite | small overlay, `.petite` section |
| FSG | tiny imports, packed sections |
| MEW | `MEW` magic in section name |
| Armadillo | runtime decryption, anti-debug (older) |

## 3. Automated unpacking

### UPX (easy)
```bash
upx -d /tmp/sample -o /tmp/unpacked
file /tmp/unpacked
```
If `upx -d` fails with "not packed by UPX", the version field has been
tampered with (anti-unpack trick). Fix:
```bash
# Patch the version byte back
python3 -c "
d = bytearray(open('/tmp/sample','rb').read())
# Find UPX! magic, fix version
import re
for m in re.finditer(b'UPX!', d):
    d[m.end()] = 0x0d  # set version field
open('/tmp/patched','wb').write(d)
"
upx -d /tmp/patched -o /tmp/unpacked
```

### ASPack
```bash
unaspack /tmp/sample  # or use ASPackDie / ASPack Stripper
```
Manual: ASPack's OEP jump is `JMP <reg>` at the end of unpack stub.
Set breakpoint there in x64dbg, dump from `Scylla` (PE only).

### MPRESS
```bash
quickunpack /tmp/sample
# Or load in x64dbg, set BP on tail jump (E9 to OEP), dump w/ Scylla
```

### PECompact / FSG
Use `unpacme` (uploads to UnpacMe service if engagement permits cloud
processing), or run in monitored sandbox + memory-dump strategy.

## 4. Manual unpacking strategy (Themida / VMProtect / Enigma)

These are commercial-grade and don't have reliable auto-unpackers.
Approach:

### Themida
1. **Static**: identify anti-debug checks, patch them or rewrite
2. **Dynamic**: x64dbg + `ScyllaHide` plugin → bypass anti-debug
3. Set hardware breakpoint on `VirtualProtect` (Themida unpacks via this)
4. When hit, walk back to find decrypted code regions
5. Dump w/ `Scylla` after OEP is reached
6. Themida often has multiple layers — repeat per layer

### VMProtect
VMProtect translates code into bytecode for a custom VM. No simple
"unpack" — you must either:
- Devirtualize (extract VM handlers + write a translator). Tools:
  `VTIL` (Vladimir's tools), `vmpfix`, manual w/ IDA + bytecode trace
- Trace + symbolic execute via `Triton` or `angr`
- Skip RE and treat as black-box (fuzz the interfaces)

### Enigma Protector
Similar to Themida. ScyllaHide handles many checks. The license / virt
machine layer is hardest. Some Enigma variants:
- v3-v5: scriptable unpack via `Enigma Static Unpacker`
- v6+: manual w/ x64dbg + Scylla, multiple decryption passes

## 5. Manual unpack technique (universal)

For any packer:
1. Disable ASLR / DEP if needed (ScyllaHide / `setdllchar`)
2. Set BP on entry point
3. Step through unpack stub; watch for:
   - Large `VirtualAlloc` (decryption region)
   - `memset` followed by decrypted code being written
   - Tail jump to OEP (often `JMP <reg>` or `RET` after PUSHAD/POPAD)
4. At suspected OEP, dump process w/ `Scylla` (PE) or `r2 -d`
5. Fix imports (Scylla auto-rebuild IAT), save dumped PE
6. Re-run static analysis on the dumped file

## 6. Anti-anti-unpacking tricks

| Anti-unpack | Counter |
|---|---|
| `IsDebuggerPresent` | ScyllaHide, or patch w/ NOP |
| `NtQueryInformationProcess`(ProcessDebugPort) | ScyllaHide |
| Timing checks (`rdtsc` measure) | x64dbg "timing" plugin or patch |
| INT3 detection (BP byte scan) | hardware BPs only |
| Self-checksum | identify check loop, patch comparison |
| TLS callbacks (run before main entry) | BP in TLS callback list (IDA: View → Open Subviews → TLS) |
| Anti-VM (CPUID hypervisor bit) | Run on bare metal or KVM w/ CPUID masking |

## 7. Promote
```
kg_add_node(kind="observation", label="packed: <packer-name>",
            props={"sample":"<sha256>","entropy":<float>,"packer":"<name>"})
kg_add_edge(src=<sample>, dst=<observation>, kind="exhibits")

# After unpack, re-run triage on the dumped file
kg_add_node(kind="artifact", label="unpacked: <sha256>",
            props={"original":"<orig-sha256>","unpacker":"<tool>"})
```

## Severity (not a vuln, but a triage gate)

| Outcome | Implication for engagement |
|---|---|
| Automated unpack succeeded → static analysis viable | Normal triage path |
| Only partial unpack (multi-layer) | Use dynamic analysis as primary |
| VMProtect / Themida heavy | Likely commercial protection — escalate effort, schedule realistically |
| Cannot unpack | Black-box fuzz + dynamic only; document static-blind constraint |

## Known exemplars
- Stuxnet: multi-layer packing including custom routines
- WannaCry: UPX + custom obfuscation
- Most commodity malware: UPX (because it's free + easy)
- Banking trojans: Themida or VMProtect common
- Cobalt Strike beacons: encrypted shellcode + reflective loader, "packer-like"
