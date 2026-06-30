---
name: ti-ioc-extraction
description: "Automated IOC extraction from threat reports, logs, and unstructured text — parse hashes, IPs, domains, URLs, email addresses, and CVEs. Covers regex-based extraction, defanging/refanging, bulk hash lookup, IOC deduplication, YARA rule generation from IOCs, and STIX/TAXII formatting for sharing."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "ioc extraction, indicator of compromise, parse hashes, extract ips, extract domains, defang, refang, ioc-finder, ioc_fanger, cyberchef, misp, stix, taxii, yara from iocs, bulk hash lookup, threat report parsing, ioc deduplication"
  tags: "ioc, extraction, threat-intelligence, defang, refang, stix, taxii, misp, hashes, domains, ips"
  mitre_attack: "T1590, T1592"
---

# IOC Extraction from Unstructured Text

Extract Indicators of Compromise from threat intelligence reports, incident logs, paste dumps, and raw text. Normalize, deduplicate, and format for downstream consumption (MISP, STIX/TAXII feeds, YARA rules, blocklists).

## Quick Reference

```bash
# Install tools
pip install ioc-finder ioc_fanger stix2 pymisp

# One-shot extraction from a report file
python3 -c "
from ioc_finder import find_iocs
text = open('/workspace/report.txt').read()
iocs = find_iocs(text)
for k,v in iocs.items():
    if v: print(f'{k}: {v}')
"

# Refang a defanged IOC list
python3 -c "
from ioc_fanger import fang
text = open('/workspace/defanged_iocs.txt').read()
print(fang(text))
" > /workspace/refanged_iocs.txt

# Quick regex extraction (no deps)
grep -oP '\b[0-9a-fA-F]{32}\b' /workspace/report.txt | sort -u > /workspace/md5_hashes.txt
grep -oP '\b[0-9a-fA-F]{64}\b' /workspace/report.txt | sort -u > /workspace/sha256_hashes.txt
grep -oP '\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b' /workspace/report.txt | sort -u > /workspace/ips.txt
```

## MITRE ATT&CK Mapping

| Technique | ID | Relevance |
|---|---|---|
| Gather Victim Network Information | T1590 | Extracted IPs, domains, and URLs map victim-facing infrastructure |
| Gather Victim Host Information | T1592 | Extracted file hashes, registry keys, and file paths indicate host-level artifacts |
| Phishing | T1566 | Extracted email addresses and sender domains from phishing report IOCs |
| Indicator Removal | T1070 | Awareness of IOC types attackers attempt to obscure or rotate |

## 1. Regex-Based IOC Extraction

When `ioc-finder` is unavailable or you need precise control, use these regex patterns:

```bash
# MD5 hashes (32 hex chars, standalone word boundary)
grep -oP '\b[0-9a-fA-F]{32}\b' /workspace/<REPORT> | sort -u > /workspace/iocs/md5.txt

# SHA1 hashes (40 hex chars)
grep -oP '\b[0-9a-fA-F]{40}\b' /workspace/<REPORT> | sort -u > /workspace/iocs/sha1.txt

# SHA256 hashes (64 hex chars)
grep -oP '\b[0-9a-fA-F]{64}\b' /workspace/<REPORT> | sort -u > /workspace/iocs/sha256.txt

# IPv4 addresses
grep -oP '\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b' \
  /workspace/<REPORT> | sort -u > /workspace/iocs/ipv4.txt

# IPv6 addresses (simplified — catches common forms)
grep -oiP '(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}:|::(?:[0-9a-f]{1,4}:){0,5}[0-9a-f]{1,4}' \
  /workspace/<REPORT> | sort -u > /workspace/iocs/ipv6.txt

# Domain names (basic, excludes common FPs)
grep -oP '(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+(?:com|net|org|io|ru|cn|xyz|top|info|biz|cc|tk|ml|ga|cf|pw|buzz|su|onion)\b' \
  /workspace/<REPORT> | sort -u > /workspace/iocs/domains.txt

# URLs (http/https/ftp)
grep -oP 'https?://[^\s"<>\])+' /workspace/<REPORT> | sort -u > /workspace/iocs/urls.txt

# Email addresses
grep -oP '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' \
  /workspace/<REPORT> | sort -u > /workspace/iocs/emails.txt

# CVE identifiers
grep -oP 'CVE-\d{4}-\d{4,7}' /workspace/<REPORT> | sort -u > /workspace/iocs/cves.txt

# MITRE ATT&CK technique IDs
grep -oP 'T\d{4}(?:\.\d{3})?' /workspace/<REPORT> | sort -u > /workspace/iocs/mitre_ids.txt
```

### False Positive Reduction

```bash
# Filter out private/reserved IPs from extracted list
grep -vP '^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.|255\.)' \
  /workspace/iocs/ipv4.txt > /workspace/iocs/ipv4_public.txt

# Filter out known benign domains (Google, Microsoft, etc.)
grep -viP '(google\.com|microsoft\.com|windowsupdate\.com|apple\.com|amazonaws\.com|cloudflare\.com)$' \
  /workspace/iocs/domains.txt > /workspace/iocs/domains_filtered.txt

# Remove hash-like strings that are too short or all-zero
grep -vP '^0{32,}$' /workspace/iocs/md5.txt | grep -vP '^(.)\1{31,}$' > /workspace/iocs/md5_clean.txt
```

## 2. Defanging and Refanging

Threat reports often defang IOCs to prevent accidental clicks. You must refang before lookups.

```bash
# Refang with ioc_fanger (Python)
python3 -c "
from ioc_fanger import fang
import sys
text = sys.stdin.read()
print(fang(text))
" < /workspace/defanged_report.txt > /workspace/refanged_report.txt

# Manual refang with sed (no deps)
sed -e 's/\[.\]/./g' \
    -e 's/hxxp/http/g' \
    -e 's/hxxps/https/g' \
    -e 's/ dot /./g' \
    -e 's/\[at\]/@/g' \
    -e 's/{dot}/./g' \
    /workspace/defanged_report.txt > /workspace/refanged_report.txt

# Defang IOCs for safe sharing
python3 -c "
from ioc_fanger import defang
import sys
text = sys.stdin.read()
print(defang(text))
" < /workspace/iocs/urls.txt > /workspace/iocs/urls_defanged.txt

# Manual defang with sed
sed -e 's/\./[.]/g' \
    -e 's|http://|hxxp://|g' \
    -e 's|https://|hxxps://|g' \
    -e 's/@/[at]/g' \
    /workspace/iocs/urls.txt > /workspace/iocs/urls_defanged.txt
```

### Common Defang Patterns to Recognize

| Original | Defanged Variants |
|---|---|
| `192.168.1.1` | `192[.]168[.]1[.]1`, `192.168.1 .1`, `192(.)168(.)1(.)1` |
| `http://evil.com` | `hxxp://evil[.]com`, `hxxp://evil(.)com`, `http[:]//evil.com` |
| `user@evil.com` | `user[at]evil[.]com`, `user[@]evil.com` |

## 3. Programmatic Extraction with ioc-finder

```bash
# Full extraction pipeline
python3 << 'PYEOF'
from ioc_finder import find_iocs
import json, sys

text = open('/workspace/<REPORT>').read()
iocs = find_iocs(text)

# Filter to populated categories only
results = {k: list(set(v)) for k, v in iocs.items() if v}

with open('/workspace/iocs/extracted.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

# Summary
for category, items in sorted(results.items()):
    print(f"  {category}: {len(items)} unique")
print(f"\nTotal categories with hits: {len(results)}")
PYEOF

# ioc-finder extracts these categories automatically:
# - md5s, sha1s, sha256s, sha512s, ssdeeps
# - ipv4s, ipv6s, urls, domains, email_addresses
# - asns, cves, registry_key_paths, file_paths
# - mac_addresses, bitcoin_addresses, xmpp_addresses
# - google_adsense_ids, google_analytics_ids
```

## 4. Bulk Hash Lookup

```bash
# VirusTotal bulk lookup (requires API key)
VT_API_KEY="<API_KEY>"
while IFS= read -r hash; do
  result=$(curl -s "https://www.virustotal.com/api/v3/files/$hash" \
    -H "x-apikey: $VT_API_KEY")
  detections=$(echo "$result" | python3 -c "
import sys, json
d = json.load(sys.stdin)
stats = d.get('data',{}).get('attributes',{}).get('last_analysis_stats',{})
print(f\"{stats.get('malicious',0)}/{sum(stats.values())}\")" 2>/dev/null)
  echo "$hash  $detections" >> /workspace/iocs/vt_results.txt
  sleep 15  # Free API: 4 requests/min
done < /workspace/iocs/sha256.txt

# MalwareBazaar lookup (free, no rate limit issues)
while IFS= read -r hash; do
  curl -s -X POST "https://mb-api.abuse.ch/api/v1/" \
    -d "query=get_info&hash=$hash" \
    -o "/workspace/iocs/mb_${hash}.json"
done < /workspace/iocs/sha256.txt

# AbuseIPDB bulk check
ABUSE_KEY="<API_KEY>"
while IFS= read -r ip; do
  result=$(curl -s "https://api.abuseipdb.com/api/v2/check?ipAddress=$ip" \
    -H "Key: $ABUSE_KEY" -H "Accept: application/json")
  score=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['abuseConfidenceScore'])" 2>/dev/null)
  echo "$ip  abuse_score=$score" >> /workspace/iocs/abuse_results.txt
done < /workspace/iocs/ipv4_public.txt
```

## 5. IOC Deduplication and Normalization

```bash
python3 << 'PYEOF'
import json, hashlib, re
from collections import defaultdict

with open('/workspace/iocs/extracted.json') as f:
    iocs = json.load(f)

deduped = {}
stats = {}

for category, items in iocs.items():
    # Normalize: lowercase domains/URLs/emails, uppercase hashes
    if category in ('md5s', 'sha1s', 'sha256s', 'sha512s'):
        normalized = sorted(set(h.lower() for h in items))
    elif category in ('domains', 'urls', 'email_addresses'):
        normalized = sorted(set(i.lower().rstrip('.') for i in items))
    elif category in ('ipv4s', 'ipv6s'):
        normalized = sorted(set(items))
    else:
        normalized = sorted(set(items))

    if normalized:
        deduped[category] = normalized
        stats[category] = {'original': len(items), 'deduped': len(normalized)}

with open('/workspace/iocs/deduped.json', 'w') as f:
    json.dump(deduped, f, indent=2)

print("Deduplication stats:")
for cat, s in sorted(stats.items()):
    removed = s['original'] - s['deduped']
    print(f"  {cat}: {s['original']} -> {s['deduped']} (removed {removed} dupes)")
PYEOF
```

## 6. STIX/TAXII Formatting

```bash
# Convert extracted IOCs to STIX 2.1 bundle
python3 << 'PYEOF'
from stix2 import (Bundle, Indicator, Identity, MarkingDefinition,
                   TLP_WHITE, TLP_GREEN, TLP_AMBER)
import json, datetime

identity = Identity(
    name="Decepticon TI Team",
    identity_class="organization"
)

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

indicators = []

# Map IOC types to STIX patterns
pattern_map = {
    'ipv4s': lambda x: f"[ipv4-addr:value = '{x}']",
    'ipv6s': lambda x: f"[ipv6-addr:value = '{x}']",
    'domains': lambda x: f"[domain-name:value = '{x}']",
    'urls': lambda x: f"[url:value = '{x}']",
    'md5s': lambda x: f"[file:hashes.MD5 = '{x}']",
    'sha1s': lambda x: f"[file:hashes.'SHA-1' = '{x}']",
    'sha256s': lambda x: f"[file:hashes.'SHA-256' = '{x}']",
    'email_addresses': lambda x: f"[email-addr:value = '{x}']",
}

for ioc_type, items in iocs.items():
    if ioc_type not in pattern_map:
        continue
    for item in items:
        indicator = Indicator(
            name=f"{ioc_type.rstrip('s').upper()}: {item}",
            pattern=pattern_map[ioc_type](item),
            pattern_type="stix",
            valid_from=datetime.datetime.now(datetime.timezone.utc),
            created_by_ref=identity.id,
            object_marking_refs=[TLP_AMBER],
            labels=["malicious-activity"]
        )
        indicators.append(indicator)

bundle = Bundle(objects=[identity] + indicators)

with open('/workspace/iocs/stix_bundle.json', 'w') as f:
    f.write(bundle.serialize(pretty=True))

print(f"STIX bundle: {len(indicators)} indicators in {len(iocs)} categories")
PYEOF
```

### Push to MISP

```bash
# Upload IOCs to MISP instance
python3 << 'PYEOF'
from pymisp import PyMISP, MISPEvent, MISPAttribute
import json

misp = PyMISP('<MISP_URL>', '<MISP_API_KEY>', ssl=False)

event = MISPEvent()
event.info = "IOCs extracted from <REPORT_NAME>"
event.distribution = 0  # Organization only
event.threat_level_id = 2  # Medium
event.analysis = 1  # Ongoing

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

type_map = {
    'ipv4s': 'ip-dst',
    'domains': 'domain',
    'urls': 'url',
    'md5s': 'md5',
    'sha1s': 'sha1',
    'sha256s': 'sha256',
    'email_addresses': 'email-src',
}

for ioc_type, items in iocs.items():
    misp_type = type_map.get(ioc_type)
    if not misp_type:
        continue
    for item in items:
        attr = MISPAttribute()
        attr.type = misp_type
        attr.value = item
        attr.to_ids = True
        event.add_attribute(**attr)

result = misp.add_event(event)
print(f"MISP event created: {result.get('Event', {}).get('id', 'ERROR')}")
PYEOF
```

## 7. CyberChef Recipes for IOC Processing

CyberChef provides browser-based IOC transforms. Key recipes for common tasks:

```
# Extract IPs — CyberChef recipe (paste into recipe URL)
Extract_IP_addresses()&Sort('Line feed',false,'Alpha')&Unique('Line feed')

# Extract URLs
Extract_URLs(false)&Sort('Line feed',false,'Alpha')&Unique('Line feed')

# Extract email addresses
Extract_email_addresses(false)&Unique('Line feed')

# Defang URLs
Defang_URL(true,true,true,'Valid domains and full URLs')

# Decode Base64-encoded IOCs (common in obfuscated reports)
From_Base64('A-Za-z0-9+/=',true,false)&Extract_IP_addresses()

# Hex-encoded IOC decode
From_Hex('Auto')&Extract_URLs(false)

# Full pipeline: decode + extract + defang + dedup
From_Base64('A-Za-z0-9+/=',true,false)&Extract_URLs(false)&Unique('Line feed')&Defang_URL()
```

## Tools & Resources

| Tool | Purpose | Install |
|---|---|---|
| ioc-finder | Python IOC extractor — 20+ IOC types | `pip install ioc-finder` |
| ioc_fanger | Defang/refang IOC strings | `pip install ioc_fanger` |
| CyberChef | Browser-based IOC transforms | `https://gchq.github.io/CyberChef/` |
| PyMISP | Python MISP API client | `pip install pymisp` |
| stix2 | STIX 2.1 Python library | `pip install stix2` |
| MalwareBazaar | Free hash lookup (abuse.ch) | API: `mb-api.abuse.ch` |
| VirusTotal | Hash/IP/domain lookup | API key required |
| AbuseIPDB | IP reputation lookup | API key required |
| ThreatFox | IOC sharing (abuse.ch) | API: `threatfox-api.abuse.ch` |

## Detection Signatures

| Pattern | Indicates | Example Match |
|---|---|---|
| `[0-9a-fA-F]{32}` | MD5 hash | `d41d8cd98f00b204e9800998ecf8427e` |
| `[0-9a-fA-F]{40}` | SHA1 hash | `da39a3ee5e6b4b0d3255bfef95601890afd80709` |
| `[0-9a-fA-F]{64}` | SHA256 hash | `e3b0c44298fc1c149afbf4c8996fb924...` |
| `hxxp[s]?://` | Defanged URL | `hxxps://evil[.]com/payload` |
| `[.]` in hostname | Defanged domain/IP | `192[.]168[.]1[.]1` |
| `CVE-\d{4}-\d{4,}` | CVE identifier | `CVE-2024-12345` |
| `T\d{4}(\.\d{3})?` | MITRE technique ID | `T1566.001` |

## Error Handling & Edge Cases

| Problem | Cause | Solution |
|---|---|---|
| Hash regex matches CSS colors | 6-char hex without word boundary | Use `\b` anchors + length check (32/40/64) |
| IP regex matches version strings | `1.2.3.4` in software versions | Cross-reference with CIDR ranges; discard private IPs if hunting external C2 |
| ioc-finder returns empty | Input encoding issue (UTF-16, BOM) | Convert to UTF-8 first: `iconv -f UTF-16 -t UTF-8` |
| VT rate limit hit | Free API = 4 req/min | Add `sleep 15` between requests; use premium key for bulk |
| STIX bundle too large | Thousands of IOCs | Split into per-type bundles or paginate |
| MISP event creation fails | SSL cert / auth error | Verify `MISP_URL`, API key, and set `ssl=False` for self-signed |
| Defanged IOCs not caught | Unusual defang format (`{dot}`, `[dot]`) | Extend sed/regex to cover vendor-specific defang styles |
| Duplicate IOCs across reports | Multiple sources, same campaign | Merge with dedup script before MISP import |

## Decision Gate

```
IF source is a PDF/DOCX threat report
  → Extract text first (pdftotext / python-docx), then run ioc-finder
IF source is a raw paste / email dump
  → Refang first (ioc_fanger), then extract
IF > 100 hashes extracted
  → Use bulk lookup (MalwareBazaar batch API) instead of per-hash VT queries
IF IOCs need sharing with external partners
  → Format as STIX 2.1 bundle with TLP marking
IF IOCs are for internal blocklist only
  → Export as flat CSV: type,value,first_seen,source
IF ioc-finder unavailable
  → Fall back to grep-based regex extraction (Section 1)
```
