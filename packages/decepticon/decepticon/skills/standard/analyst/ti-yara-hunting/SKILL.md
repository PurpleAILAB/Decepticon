---
name: ti-yara-hunting
description: "YARA rule writing from behavioral observations and TI report analysis — sample-to-rule conversion, condition optimization, performance tuning, and retrohunting on VirusTotal and ANY.RUN. Covers YARA/YARA-X syntax, yarGen automated generation, and production rule deployment."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "yara, yara rule, yara-x, yargen, retrohunt, retrohunting, virustotal hunting, anyrun yara search, malware signature, malware hunting, yara condition, yara strings, threat hunting rules, livehunt"
  tags: "yara, hunting, threat-intelligence, retrohunt, virustotal, anyrun, malware-detection, yargen"
  mitre_attack: "T1588.005"
---

# YARA Hunting

Write YARA rules from malware samples, behavioral observations, and threat intelligence reports. Deploy rules for retrohunting across VirusTotal (500M+ files) and ANY.RUN (2TB malware corpus) to discover campaign variants, earlier versions, and related infrastructure.

## Quick Reference

```bash
# Install YARA
apt-get install -y yara || pip install yara-python

# Install YARA-X (Rust rewrite — faster, stricter)
cargo install yara-x

# Install yarGen for automated rule generation
git clone https://github.com/Neo23x0/yarGen.git /opt/yarGen
cd /opt/yarGen && pip install -r requirements.txt
python3 yarGen.py --update  # Download goodware string DB (first run only)

# Scan a file with a rule
yara /workspace/rules/suspect.yar /workspace/samples/

# Compile rules for faster scanning
yarac /workspace/rules/*.yar /workspace/rules/compiled.yarc
yara /workspace/rules/compiled.yarc /workspace/samples/

# Validate rule syntax (YARA-X — stricter parser)
yr check /workspace/rules/suspect.yar
```

## MITRE ATT&CK Mapping

| Technique | ID | Relevance |
|---|---|---|
| Obtain Capabilities: Exploits | T1588.005 | YARA identifies exploit tools/payloads in attacker arsenals |
| Develop Capabilities: Malware | T1587.001 | Rules detect custom malware based on unique strings/structures |
| Gather Victim Host Information: Software | T1592.002 | YARA scans reveal installed malware on victim hosts |
| Indicator Removal on Host | T1070 | Retrohunting finds samples attackers attempted to erase |

## 1. YARA Rule Syntax

### Minimal Rule Structure

```yara
rule Malware_FamilyName_Variant {
    meta:
        author      = "Decepticon TI"
        date        = "2025-01-01"
        description = "Detects FamilyName variant based on unique strings"
        hash        = "e3b0c44298fc1c149afbf4c8996fb924..."
        reference   = "https://report-url"
        tlp         = "WHITE"

    strings:
        $s1 = "unique_string_from_sample" ascii wide
        $s2 = { 4D 5A 90 00 03 00 00 00 }  // MZ header + specific bytes
        $s3 = /https?:\/\/[a-z0-9\-\.]+\/gate\.php/ nocase

    condition:
        uint16(0) == 0x5A4D and    // PE file check
        filesize < 5MB and
        2 of ($s*)
}
```

### String Types

```yara
strings:
    // Text strings
    $text1 = "CreateRemoteThread"           // ASCII exact
    $text2 = "CreateRemoteThread" ascii wide // Both encodings
    $text3 = "http://c2.evil.com" nocase    // Case insensitive
    $text4 = "cmd /c" fullword              // Word boundary match

    // Hex strings (byte patterns)
    $hex1 = { 48 8B 05 ?? ?? ?? ?? }        // ?? = any byte (wildcard)
    $hex2 = { 4D 5A [0-200] 50 45 00 00 }   // Jump 0-200 bytes
    $hex3 = { ( 74 | 75 ) 0? }              // Alternation: je or jne

    // Regex strings
    $re1 = /https?:\/\/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\/[a-z]+\.php/
    $re2 = /[A-Za-z0-9+\/]{50,}={0,2}/      // Base64 blob

    // XOR-encoded strings (YARA 4.0+)
    $xor1 = "This program cannot" xor       // All single-byte XOR keys
    $xor2 = "config_url" xor(0x01-0xFF)     // Specific XOR range

    // Base64-encoded strings (YARA 4.0+)
    $b64 = "powershell" base64 base64wide
```

### Condition Essentials

```yara
condition:
    // File type guards (always lead with these)
    uint16(0) == 0x5A4D                     // PE (MZ header)
    uint32(0) == 0x464C457F                 // ELF
    uint16(0) == 0x4B50                     // ZIP/DOCX/XLSX (PK)

    // String matching
    all of them                             // Every string must match
    any of them                             // At least one
    2 of ($s*)                              // 2+ from $s group
    3 of ($api*) and 1 of ($str*)           // Mixed groups
    #s1 > 5                                 // $s1 appears 5+ times

    // Size + offset constraints
    filesize < 1MB
    $mz at 0                                // $mz must be at offset 0
    $s1 in (0..1024)                        // $s1 in first 1KB

    // PE module (import pe)
    pe.imports("kernel32.dll", "VirtualAlloc")
    pe.number_of_sections > 6

    // Math module (import math)
    math.entropy(0, filesize) > 7.0         // High entropy (packed)

    // Typical combined condition
    uint16(0) == 0x5A4D and filesize < 2MB and
    (2 of ($s*) or all of ($api*))
```

## 2. Writing Rules from Malware Samples

### Step-by-Step: Sample to Rule

```bash
# Step 1: Extract strings from sample
strings -n 6 /workspace/samples/<SAMPLE> > /workspace/rules/strings_raw.txt
strings -n 6 -el /workspace/samples/<SAMPLE> >> /workspace/rules/strings_raw.txt  # Wide strings

# Step 2: Identify unique strings (not in common binaries)
# Look for: C2 URLs, mutex names, PDB paths, custom error messages,
# registry keys, file paths, encryption keys, config markers
grep -iP '(http|ftp|\.php|\.aspx|mutex|pdb|\\\\Users|HKEY_|config|beacon|payload)' \
  /workspace/rules/strings_raw.txt | sort -u > /workspace/rules/strings_interesting.txt

# Step 3: Extract hex patterns at key offsets
xxd /workspace/samples/<SAMPLE> | head -50  # File header
xxd -s 0x400 -l 256 /workspace/samples/<SAMPLE>  # Code section start

# Step 4: Check PE imports (if PE file)
python3 -c "
import pefile
pe = pefile.PE('/workspace/samples/<SAMPLE>')
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll = entry.dll.decode()
    for imp in entry.imports:
        name = imp.name.decode() if imp.name else str(imp.ordinal)
        print(f'{dll}:{name}')
" > /workspace/rules/imports.txt

# Step 5: Check entropy per section
python3 -c "
import pefile, math
pe = pefile.PE('/workspace/samples/<SAMPLE>')
for s in pe.sections:
    name = s.Name.rstrip(b'\x00').decode(errors='replace')
    data = s.get_data()
    if data:
        ent = sum(-p*math.log2(p) for p in [data.count(bytes([b]))/len(data) for b in range(256)] if p > 0)
        print(f'{name}: entropy={ent:.2f} size={len(data)}')
"
```

### Template: Rule from Behavioral Observations

```yara
rule APT_Backdoor_ObservedBehavior {
    meta:
        author      = "Decepticon TI"
        date        = "2025-01-01"
        description = "Backdoor observed during engagement — drops to %TEMP%, "
                      "contacts C2 over HTTPS, exfiltrates via DNS TXT"
        tlp         = "AMBER"

    strings:
        // Observed C2 communication pattern
        $c2_uri  = "/api/v1/check" ascii
        $c2_ua   = "Mozilla/5.0 (compatible; MSIE 10.0)" ascii

        // Observed mutex (from dynamic analysis)
        $mutex   = "Global\\{8A4E2C-" ascii

        // Observed file drops
        $drop1   = "\\AppData\\Local\\Temp\\svchost32.exe" ascii wide
        $drop2   = "\\ProgramData\\Microsoft\\updater.dll" ascii wide

        // Observed registry persistence
        $reg     = "Software\\Microsoft\\Windows\\CurrentVersion\\Run" ascii wide

        // DNS exfiltration pattern (hex-encoded subdomain)
        $dns_exf = /[0-9a-f]{16,}\.data\.[a-z0-9\-]+\.(com|net|org)/

        // Encryption routine bytes (from disassembly)
        $crypto  = { 8B 45 ?? 33 45 ?? 89 45 ?? 8B 4D ?? 03 4D ?? }

    condition:
        uint16(0) == 0x5A4D and
        filesize < 3MB and
        ($mutex or $crypto) and
        2 of ($c2_*, $drop*, $reg, $dns_exf)
}
```

## 3. Automated Rule Generation with yarGen

```bash
# Generate rule from single sample
python3 /opt/yarGen/yarGen.py \
  -m /workspace/samples/<SAMPLE> \
  -o /workspace/rules/yargen_output.yar \
  --excludegood

# Generate rules from directory of related samples
python3 /opt/yarGen/yarGen.py \
  -m /workspace/samples/campaign_x/ \
  -o /workspace/rules/campaign_x.yar \
  --excludegood \
  -a "Decepticon TI" \
  -r "https://engagement-reference"

# AI-assisted mode (v0.24.0+) — generates expanded string set with AI prompt
python3 /opt/yarGen/yarGen.py \
  -m /workspace/samples/<SAMPLE> \
  -o /workspace/rules/yargen_ai.yar \
  --ai

# Inverse match — generate rule for goodware (detect clean files)
python3 /opt/yarGen/yarGen.py \
  -m /workspace/samples/<SAMPLE> \
  -o /workspace/rules/yargen_output.yar \
  --inverse --excludegood

# After generation: review and tighten the rule
# yarGen over-selects strings — prune to 5-15 high-confidence indicators
# Add file type checks (uint16(0) == 0x5A4D) and size constraints
```

### yarGen Output Review Checklist

1. **Remove generic strings** — `"Microsoft"`, `"Windows"`, `"kernel32.dll"` add nothing
2. **Keep unique artifacts** — PDB paths, mutex names, custom headers, C2 URIs
3. **Add file type guard** — `uint16(0) == 0x5A4D` for PE, `uint32(0) == 0x464C457F` for ELF
4. **Add size constraint** — `filesize < 10MB` prevents scanning huge archives
5. **Tighten condition** — change `all of them` to `N of ($s*)` to tolerate variants
6. **Test against goodware** — scan `/usr/bin/`, `C:\Windows\System32\` for false positives

## 4. Condition Optimization and Performance

1. **Always lead with cheap checks**: `uint16(0) == 0x5A4D and filesize < 5MB and ...`
2. **Anchor strings to offsets**: `$mz at 0`, `$config in (filesize - 4096 .. filesize)`
3. **Bound regex**: `/.{0,1000}evil/` causes backtracking; use `/evil[a-z]{0,20}\.php/`
4. **Prefer hex over regex** for bytes: `{ 4D 5A [0-500] 50 45 }` > `/\x4D\x5A.{0,500}\x50\x45/`
5. **Threshold matching**: `3 of ($s*)` instead of `all of them` — tolerates variant mutations
6. **PE module for imports**: `pe.imports("ws2_32.dll", "connect")` beats string-matching DLL names

```bash
# Test for false positives against goodware
yara -r /workspace/rules/suspect.yar /usr/bin/ 2>/dev/null | wc -l  # Target: 0
yr scan --profile /workspace/rules/suspect.yar /workspace/samples/  # YARA-X profiling
```

## 5. TI Report-to-YARA Conversion

Use the `ti-ioc-extraction` skill to extract IOCs from reports, then build YARA:
- **Hashes** → `meta:` section (for reference/correlation, not detection)
- **Domains/URLs** → text strings with `ascii nocase`
- **File paths** → text strings with `ascii wide` (escape backslashes)
- **Snort/Suricata content matches** → YARA text strings (e.g., `content:"/gate.php"` → `$uri = "/gate.php" ascii`)

## 6. Retrohunting Workflows

### VirusTotal Retrohunt

```bash
# Submit retrohunt job via API
VT_API_KEY="<API_KEY>"

# Upload rule
curl -s -X POST "https://www.virustotal.com/api/v3/intelligence/retrohunt_jobs" \
  -H "x-apikey: $VT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "type": "retrohunt_job",
      "attributes": {
        "rules": "rule test { strings: $s = \"unique_marker\" condition: $s }",
        "notification_email": "analyst@example.com",
        "corpus": "main",
        "time_range": { "start": 1700000000, "end": 1710000000 }
      }
    }
  }' > /workspace/hunting/retrohunt_job.json

# Check job status
JOB_ID=$(python3 -c "import json; print(json.load(open('/workspace/hunting/retrohunt_job.json'))['data']['id'])")
curl -s "https://www.virustotal.com/api/v3/intelligence/retrohunt_jobs/$JOB_ID" \
  -H "x-apikey: $VT_API_KEY" | python3 -m json.tool

# Retrieve matches (after job completes — typically 2-3 hours)
curl -s "https://www.virustotal.com/api/v3/intelligence/retrohunt_jobs/$JOB_ID/matching_files?limit=40" \
  -H "x-apikey: $VT_API_KEY" > /workspace/hunting/retrohunt_matches.json
```

**VirusTotal Retrohunt Limits:**
- Corpus: 500M+ files (~680TB), scanned in 2-3 hours
- Hunting Pro: 12-month lookback | Standard: 3-month lookback
- Max 300 rules per job, total rule text < 1MB
- Max 10,000 matches per job
- LiveHunt (real-time): rules tested against every new upload

### VirusTotal LiveHunt (Real-Time)

```bash
# Create a LiveHunt ruleset — rules tested against every new VT upload
curl -s -X POST "https://www.virustotal.com/api/v3/intelligence/hunting_rulesets" \
  -H "x-apikey: $VT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"data":{"type":"hunting_ruleset","attributes":{"name":"Campaign_X_Tracker","enabled":true,"rules":"rule Campaign_X { strings: $c2 = \"evil-c2.example.com\" condition: uint16(0) == 0x5A4D and $c2 }","notification_emails":["analyst@example.com"]}}}'
```

### ANY.RUN YARA Search

```bash
# Web interface: https://yara.any.run/
# 1. Paste YARA rule into editor (syntax highlighting, multi-tab)
# 2. Click "Search" — scans 2TB malware corpus
# 3. Results link to sandbox sessions (interactive execution replay)
# 4. Free tier: 20 YARA Search requests (shared with TI Lookup quota)

# API submission
curl -s "https://api.any.run/v1/yara/search" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule": "rule test { strings: $s = \"unique_marker\" ascii condition: $s }"
  }' > /workspace/hunting/anyrun_yara_results.json

# Results include sandbox session UUIDs — open for full analysis:
# https://app.any.run/tasks/<UUID>
```

### Retrohunting End-to-End

```bash
# 1. Write rule from engagement sample (Section 2)
# 2. Validate locally — must match known sample, must NOT match goodware
yara /workspace/rules/campaign.yar /workspace/samples/
yara /workspace/rules/campaign.yar /usr/bin/ 2>/dev/null  # Expect 0 matches

# 3. Submit to VT Retrohunt (historical) + ANY.RUN YARA Search (sandbox corpus)
# 4. Deploy as VT LiveHunt for ongoing monitoring
# 5. Collect + deduplicate matches from both platforms
# 6. Download new samples for deeper analysis
```

## 7. YARA-X Differences

YARA-X (Rust rewrite) offers stricter parsing, better performance, and multi-line metadata (0.4.0+). Key commands:

```bash
cargo install yara-x          # Install
yr check /workspace/rules/*.yar  # Validate (catches bugs classic YARA ignores)
yr scan /workspace/rules/*.yar /workspace/samples/  # Scan
```

If classic YARA accepts a rule but YARA-X rejects it, fix the rule — the stricter parser catches real syntax bugs.

## Tools & Resources

| Tool | Purpose | Install/URL |
|---|---|---|
| yara | Rule scanning engine | `apt install yara` |
| yarac | Compile rules to binary | Ships with yara |
| YARA-X | Rust rewrite — stricter, faster | `cargo install yara-x` |
| yarGen | Auto-generate rules from samples | `github.com/Neo23x0/yarGen` |
| yarGen-Go | Go rewrite of yarGen | `github.com/Neo23x0/yarGen-Go` |
| yara-python | Python bindings | `pip install yara-python` |
| VT Retrohunt | Scan 500M+ historical files | `virustotal.com` (paid) |
| VT LiveHunt | Real-time rule matching on uploads | `virustotal.com` (paid) |
| ANY.RUN YARA Search | Scan 2TB malware corpus | `yara.any.run` |
| YARA rules repo (ANY.RUN) | Community detection rules | `github.com/anyrun/YARA` |
| awesome-yara | Curated rule/tool list | `github.com/InQuest/awesome-yara` |

## Detection Signatures

| Rule Pattern | Detects | False Positive Risk |
|---|---|---|
| `uint16(0) == 0x5A4D and pe.imports("ntdll.dll", "NtCreateThreadEx")` | Process injection via direct syscall | Low — legitimate use rare |
| `$s xor(0x01-0xFF)` | Single-byte XOR-encoded strings | Medium — scan time increases |
| `math.entropy(0, filesize) > 7.5` | Packed/encrypted payloads | Medium — compressed archives also match |
| `pe.number_of_signatures == 0 and pe.timestamp > X` | Unsigned recent PE | High — many legitimate unsigned binaries |
| `filesize < 50KB and pe.imports("ws2_32.dll")` | Small network-capable binary | Low — shellcode droppers are typically small |

## Error Handling & Edge Cases

| Problem | Cause | Solution |
|---|---|---|
| Rule compiles but matches nothing | Strings not present in target encoding | Add `ascii wide` to text strings; check endianness for hex |
| Too many false positives | Overly generic strings | Add file type guard, size constraint, and tighten to `N of ($s*)` |
| yarGen produces 100+ string rule | Default behavior — includes everything | Prune to 5-15 high-confidence strings; add manual conditions |
| Retrohunt job times out | Rule too complex or regex too broad | Simplify regex; add `filesize <` guard; split into multiple jobs |
| YARA-X rejects valid YARA rule | Stricter parser | Fix deprecated syntax (e.g., unescaped special chars in regex) |
| Hex pattern `??` matches too broadly | Wildcards without anchoring | Add surrounding fixed bytes; use `[N-M]` jumps instead |
| PE module unavailable in sandbox | YARA compiled without PE module | Use `uint16(0) == 0x5A4D` as fallback; check `yara --help` for modules |
| LiveHunt notifications delayed | VT processing backlog | Normal during high-volume periods; check dashboard |
| Rule works locally but not on VT | Module version mismatch | Check VT supported YARA version and modules |

## Decision Gate

```
IF you have a malware sample on disk
  → Extract strings + imports → write rule manually (Section 2)
  → Then run yarGen for additional string candidates (Section 3)
IF you have a TI report with IOCs but no sample
  → Extract IOCs (ti-ioc-extraction skill) → build string-based rule (Section 5)
IF you need to find campaign variants in the wild
  → Submit rule to VT Retrohunt (historical) + ANY.RUN YARA Search (Section 6)
IF you need ongoing monitoring for new variants
  → Deploy as VT LiveHunt rule (Section 6)
IF rule produces false positives
  → Add file type check, size constraint, raise string threshold (Section 4)
IF yarGen output is too noisy
  → Prune to 5-15 unique strings, add PE/ELF header check, test against goodware
IF performance is poor on large corpus
  → Lead condition with uint16/filesize check; replace regex with hex patterns (Section 4)
IF classic YARA accepts but YARA-X rejects
  → Fix the rule — YARA-X catches real bugs; the stricter parser is correct
```
