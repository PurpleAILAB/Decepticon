---
name: reverser-yara-hunting
description: "YARA rule authoring + hunting — `condition:` syntax, hex patterns with wildcards, `for`/`any of them`, PE module, ELF module, hash module, math module. Build per-family signatures, hunt at scale via VT/MalwareBazaar/Hybrid Analysis. Avoid common pitfalls (collisions, slow rules, regex traps)."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "yara rule signature hunting virustotal vt malshare malwarebazaar hybrid analysis pe elf hash condition any all of"
  subdomain: reverser
  tags: yara, malware, hunting, signatures
  mitre_attack: T1518.001
---

# YARA Rule Authoring + Hunting

## Anatomy of a good rule

```yara
import "pe"
import "hash"

rule MalFamily_DropperVariant_Q4_2024 {
    meta:
        author = "you"
        date = "2024-11-20"
        description = "MalFamily dropper, observed Q4 2024 campaign"
        hash = "deadbeefdeadbeefdeadbeefdeadbeef"
        tlp = "amber"
        confidence = "high"
        false_positives = "low (test against AV vendor samples)"
        mitre = "T1055"

    strings:
        $magic = { 4D 5A 90 00 03 }            // MZ + DOS header
        $config_marker = { 7A 89 ?? ?? 4F 8C } // 6-byte signature, 2 wildcards
        $string1 = "loader_stage_2" wide
        $string2 = "cmd.exe /c " ascii
        $api1   = "VirtualAllocEx"
        $api2   = "WriteProcessMemory"
        $api3   = "CreateRemoteThread"
        // Avoid generic strings — they cause FPs.

    condition:
        uint16(0) == 0x5A4D and                    // PE header
        filesize < 5MB and                          // bounded — avoids huge-file scans
        $config_marker and                          // unique marker
        2 of ($api1, $api2, $api3) and             // at least 2 of the 3 process-inject APIs
        any of ($string*) and
        pe.imports("ws2_32.dll", "WSAStartup") and  // network capability
        not pe.is_signed                            // unsigned
}
```

## The condition tools you need

```yara
// Filesize / offset reads (no module)
filesize > 100KB and filesize < 5MB
uint32(0x3c) > 0 and uint32(uint32(0x3c)) == 0x4550  // valid PE

// "for" loops over offsets / sections
for any i in (0..pe.number_of_sections - 1):
    (pe.sections[i].name == ".text" and pe.sections[i].entropy > 7.0)

// "of"
1 of them                              // any one string
all of ($a*)                           // all $a*-prefix strings
3 of ($s1, $s2, $s3, $s4, $s5)         // at least 3 of 5

// Hash module
hash.sha256(0, filesize) == "..."      // exact-match rule
hash.imphash() == "..."                // PE import hash (fragile but high-signal)
```

## High-leverage patterns

### Family-stable byte patterns
Look for unique byte sequences that survive obfuscation:
- Crypto constants (SHA-256 IVs, AES sbox, RC4 init pattern)
- Hard-coded SID strings
- C2 packet headers (magic bytes, fixed offsets)
- Reflective loader entry stub bytes (Donut, Cobalt Strike's PE loader)

### Capability rules
Don't fingerprint a sample — fingerprint a TECHNIQUE:

```yara
rule Suspicious_ProcessInjection {
    meta: description = "VirtualAlloc + WriteProcessMemory + CreateRemoteThread = injection"
    condition:
        pe.imports("kernel32.dll", "VirtualAllocEx") and
        pe.imports("kernel32.dll", "WriteProcessMemory") and
        pe.imports("kernel32.dll", "CreateRemoteThread")
}
```

This catches every injector regardless of family. False-positive: legitimate tools (Procmon, IDA, debuggers). Reduce via additional conditions (unsigned, in temp dir, etc.).

### Anti-analysis fingerprinting
```yara
rule AntiVm_VMware_Strings {
    strings:
        $s1 = "VMware" ascii nocase
        $s2 = "VBoxService" ascii nocase
        $s3 = "qemu" ascii nocase
        $s4 = { 56 4D 58 68 } // "VMXh" — VMware backdoor port magic
    condition: 2 of them
}
```

## Hunting at scale

### VirusTotal Retrohunt (paid)
```yara
// Upload rule to VT — runs against the past 90 days of submissions
// Outputs new hashes matching the signature
```

### MalwareBazaar (free)
```bash
# yarafs.io / abuse.ch — runs YARA against MB corpus
curl https://mb-api.abuse.ch/api/v1/ -X POST -d 'query=get_yara&yara_rule=YourRule'
```

### Local corpus scan
```bash
# Recursive scan
yara -r rules/ /samples/
# JSON output for downstream processing
yara -r rules/ /samples/ -m -p 4    # -m: metadata, -p: parallel threads

# Fast pre-filter with capa first
capa /samples/sample.exe   # extracts capabilities; rule-driven, JSON-output
```

## Common pitfalls

| Pitfall | Fix |
|---|---|
| Too-short strings (4 bytes) → false positives | Use 8+ byte strings; require multiple matches |
| Regex `/pattern/` with `[`, `?`, `*` → slow | Prefer literal strings; if regex needed, anchor with `^`/`\b` |
| No filesize bound → scans 5GB files | Always include `filesize < N` |
| Multiple wildcards in one hex `??` → exponential matcher cost | Limit to 2-3 wildcards per byte string |
| `condition: any of them` with one common string → constant FPs | Use `2 of them` minimum |
| Rule name with version | Use a separate `meta.version` so rule survives bumps |

## Mass-hunt workflow

1. Triage a sample (see `reverser/malware-triage` skill)
2. Extract unique byte patterns, strings, capabilities
3. Write a YARA rule with `meta` for context + bounded `condition`
4. Test against:
   - The known sample (must match)
   - A clean corpus (must NOT match — false positive rate)
   - A different malware family corpus (must NOT match)
5. Submit to VT Retrohunt + MalwareBazaar
6. Track results, iterate

## Tooling

- `yara` / `yara-python` (writing + running)
- `yarGen` (auto-generate rules from a sample set)
- `valhalla.nextron-systems.com` (commercial YARA feed by Florian Roth)
- `Neo23x0/signature-base` (open-source canonical rule set)
- `capa` (Mandiant — capability-level rules)

## References

- VirusTotal YARA guide
- "YARA, the pattern matching swiss knife for malware researchers"
- Florian Roth's blog (the canonical YARA author of our era)
- "Practical YARA Rules" — Andre Tavares
