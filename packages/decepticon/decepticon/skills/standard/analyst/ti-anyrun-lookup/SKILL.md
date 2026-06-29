---
name: ti-anyrun-lookup
description: "ANY.RUN Threat Intelligence Lookup workflow — query hashes, domains, IPs, and behavioral indicators against ANY.RUN's sandbox corpus. Covers TI Lookup query syntax, search operators, free tier constraints, result correlation with engagement findings, and integration with sandbox analysis."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "anyrun, any.run, ti lookup, threat intelligence lookup, sandbox lookup, hash lookup, domain lookup, behavioral search, filePath, commandLine, domainName, suricataMessage, anyrun api, sandbox correlation"
  tags: "anyrun, threat-intelligence, sandbox, ti-lookup, ioc-lookup, behavioral-search"
  mitre_attack: "T1590, T1592"
---

# ANY.RUN TI Lookup

ANY.RUN's Threat Intelligence Lookup searches across sandbox analysis sessions to correlate IOCs, behavioral indicators, and detection signatures. Unlike static hash databases, results link directly to interactive sandbox sessions showing full execution traces.

This is an **analyst workflow skill** — it describes how to use the TI Lookup web interface and API to enrich engagement findings, not a tool integration.

## Quick Reference

```bash
# API query — hash lookup
curl -s "https://api.any.run/v1/intelligence/lookup" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "sha256:\"<HASH>\""}' | python3 -m json.tool

# API query — domain lookup
curl -s "https://api.any.run/v1/intelligence/lookup" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "domainName:\"<DOMAIN>\""}' | python3 -m json.tool

# API query — IP lookup
curl -s "https://api.any.run/v1/intelligence/lookup" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "destinationIP:\"<IP>\""}' | python3 -m json.tool

# Web interface
# https://intelligence.any.run/ — paste IOC into search bar
```

## MITRE ATT&CK Mapping

| Technique | ID | Relevance |
|---|---|---|
| Gather Victim Network Information | T1590 | Domain/IP lookups reveal victim-facing infrastructure seen in sandbox sessions |
| Gather Victim Host Information | T1592 | File hash and path lookups reveal host artifacts from detonated samples |
| Active Scanning | T1595 | Correlate engagement scan results with known sandbox-observed behaviors |
| Search Open Technical Databases | T1596 | TI Lookup acts as a searchable database of real malware executions |

## 1. TI Lookup Query Syntax

### Field-Based Search

Queries use `fieldName:"value"` syntax. Combine with logical operators.

```
# Hash lookups (exact match)
sha256:"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
sha1:"da39a3ee5e6b4b0d3255bfef95601890afd80709"
md5:"d41d8cd98f00b204e9800998ecf8427e"

# Network indicators
domainName:"evil-c2.example.com"
destinationIP:"198.51.100.42"
url:"http://evil-c2.example.com/gate.php"

# File paths (use double backslash to escape)
filePath:"C:\\Users\\Public\\payload.exe"
filePath:"*\\AppData\\Roaming\\*.exe"

# Process command lines
commandLine:"powershell.exe -enc*"
commandLine:"cmd.exe /c whoami"
commandLine:"*certutil*-urlcache*"

# Registry modifications
registryKey:"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\*"
registryName:"Debugger"
registryValue:"*cmd.exe*"

# Detection names and Suricata signatures
detectionName:"Trojan.GenericKD*"
suricataMessage:"ET MALWARE*"
suricataSID:"2024001"

# MITRE ATT&CK technique search
mitreTechnique:"T1059.001"

# Threat tags
threatName:"AgentTesla"
threatName:"Emotet"
```

### Logical Operators

```
# AND — both conditions must match
domainName:"evil.com" AND destinationIP:"198.51.100.42"

# OR — either condition matches
sha256:"<HASH1>" OR sha256:"<HASH2>"

# NOT — exclude results
commandLine:"powershell*" NOT filePath:"*\\System32\\*"

# Grouping with parentheses
(domainName:"evil.com" OR domainName:"evil2.com") AND threatName:"Emotet"

# Complex query example — find samples that contact a C2 AND run PowerShell
domainName:"suspect-c2.example.com" AND commandLine:"powershell*"
```

### Wildcard Characters

| Wildcard | Meaning | Example |
|---|---|---|
| `*` | Any number of characters (including none) | `filePath:"*\\Temp\\*.exe"` |
| `?` | Exactly one character or none | `domainName:"evil?.com"` |
| `^` | Must start with (anchor start) | `commandLine:"^powershell"` |
| `$` | Must end with (anchor end) | `filePath:"*.dll$"` |

```
# Files dropped in any user's Temp folder
filePath:"C:\\Users\\*\\AppData\\Local\\Temp\\*"

# Domains matching a pattern
domainName:"*.evil-infrastructure.com"

# Commands starting with specific binary
commandLine:"^reg.exe*"

# Files ending with specific extension
fileName:"*.hta$"
```

## 2. Free Tier Limitations

| Feature | Free Plan | Paid Plans |
|---|---|---|
| TI Lookup requests | 20 premium requests | Unlimited |
| Search fields | Basic (hashes, URLs, domains, IPs, MITRE, Suricata IDs) + AND | All 40+ fields + AND/OR/NOT |
| Results per query | 10 most recent sandbox sessions | Full history |
| IOC/IOB/IOA detail | Full details from 10 most recent sessions | Full access all sessions |
| YARA Search requests | 20 (shared pool with TI Lookup) | Unlimited |
| API access | Limited | Full REST API |
| Response time | ~2-5 seconds | ~2 seconds |

### Working Within Free Tier

```
# Maximize 20 requests: batch related IOCs with OR
sha256:"<HASH1>" OR sha256:"<HASH2>" OR sha256:"<HASH3>"

# Use basic fields that don't consume premium quota
# Free unlimited: file hashes, URLs, domains, IPs, MITRE techniques, Suricata IDs

# Prioritize lookups — check the most suspicious IOC first
# If a hash returns sandbox sessions, explore those sessions for related IOCs
# (exploring linked sessions in the web UI is free browsing, not a query)
```

## 3. Search Operator Recipes

### Malware Family Identification

```
# Match a hash to known malware family
sha256:"<HASH>" 

# If result includes threatName, pivot on it:
threatName:"AgentTesla"

# Find all samples of a family that contacted specific infrastructure
threatName:"QakBot" AND domainName:"*.example.com"
```

### Behavioral Indicator Hunting

```
# Living-off-the-land binary abuse
commandLine:"*mshta*http*"
commandLine:"*certutil*-urlcache*-split*"
commandLine:"*bitsadmin*/transfer*"
commandLine:"*regsvr32*/s*/n*/u*/i:http*"

# Persistence mechanisms
registryKey:"*\\CurrentVersion\\Run\\*" AND commandLine:"powershell*"

# Credential access patterns
commandLine:"*sekurlsa*" OR commandLine:"*mimikatz*"
filePath:"*\\lsass*.dmp"

# Discovery commands
commandLine:"*net user*/domain*" AND commandLine:"*nltest*"
```

### Network Infrastructure Correlation

```
# Find all samples contacting an IP
destinationIP:"<IP>"

# Find domains resolved to an IP
domainName:"*" AND destinationIP:"<IP>"

# Suricata-flagged traffic to engagement infrastructure
suricataMessage:"*<KEYWORD>*" AND destinationIP:"<IP>"

# Port-based filtering
destinationPort:"4444" AND destinationIP:"<IP>"
```

## 4. Correlating with Engagement Findings

### Workflow: Hash Found on Compromised Host

```bash
# Step 1: Look up the hash in TI Lookup
curl -s "https://api.any.run/v1/intelligence/lookup" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -d '{"query": "sha256:\"<HASH>\""}' > /workspace/ti/hash_result.json

# Step 2: Extract key fields from result
python3 << 'PYEOF'
import json

with open('/workspace/ti/hash_result.json') as f:
    data = json.load(f)

for task in data.get('data', {}).get('tasks', []):
    print(f"Task ID:     {task.get('uuid')}")
    print(f"Verdict:     {task.get('verdict')}")
    print(f"Threat:      {task.get('threatName', 'Unknown')}")
    print(f"Tags:        {', '.join(task.get('tags', []))}")
    print(f"Created:     {task.get('date')}")
    print(f"Sandbox URL: https://app.any.run/tasks/{task.get('uuid')}")
    print("---")
PYEOF

# Step 3: If match found, open sandbox session in browser for:
#   - Full process tree
#   - Network connections (C2 IPs/domains)
#   - Dropped files (additional IOCs)
#   - Registry modifications
#   - MITRE ATT&CK mapping
```

### Workflow: Suspicious Domain from Network Logs

```bash
# Step 1: Query domain
curl -s "https://api.any.run/v1/intelligence/lookup" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -d '{"query": "domainName:\"<DOMAIN>\""}' > /workspace/ti/domain_result.json

# Step 2: Cross-reference with engagement timeline
python3 << 'PYEOF'
import json

with open('/workspace/ti/domain_result.json') as f:
    ti_data = json.load(f)

# Extract all hashes that contacted this domain
related_hashes = set()
for task in ti_data.get('data', {}).get('tasks', []):
    for ioc in task.get('iocs', {}).get('sha256', []):
        related_hashes.add(ioc)
    print(f"Malware family: {task.get('threatName', 'N/A')}")
    print(f"  Contacted domain at: {task.get('date')}")

if related_hashes:
    print(f"\nRelated file hashes ({len(related_hashes)}):")
    for h in sorted(related_hashes):
        print(f"  {h}")
    # Check these hashes against host forensic images
PYEOF
```

### Workflow: Pivot from C2 IP

```bash
# Step 1: Find all sandbox sessions that connected to the IP
curl -s "https://api.any.run/v1/intelligence/lookup" \
  -H "Authorization: API-Key <ANYRUN_API_KEY>" \
  -d '{"query": "destinationIP:\"<IP>\""}' > /workspace/ti/ip_result.json

# Step 2: Build IOC cluster
python3 << 'PYEOF'
import json

with open('/workspace/ti/ip_result.json') as f:
    data = json.load(f)

domains = set()
hashes = set()
families = set()

for task in data.get('data', {}).get('tasks', []):
    families.add(task.get('threatName', 'Unknown'))
    # Collect all associated IOCs for the engagement report

print(f"Malware families using this IP: {families}")
print(f"Use sandbox session URLs to extract dropped file hashes and additional C2 domains")
PYEOF
```

## 5. Integrating with Sandbox Analysis

When TI Lookup returns a match, the linked sandbox session provides deeper context:

### Manual Web UI Workflow

1. **Search** at `https://intelligence.any.run/` — paste IOC
2. **Review results** — each row is a sandbox session with verdict, threat name, tags
3. **Click session** → opens interactive sandbox replay showing:
   - Process tree (parent → child execution chain)
   - Network activity (DNS queries, HTTP requests, TCP connections)
   - File system changes (dropped/modified files)
   - Registry modifications
   - MITRE ATT&CK techniques triggered
4. **Extract IOCs** from session — click "IOC" tab for auto-extracted indicators
5. **Download PCAP** — network capture from sandbox run for offline analysis
6. **Export report** — PDF/JSON for inclusion in engagement deliverables

### Submitting New Samples to Sandbox

```
# Web submission: https://app.any.run/
# 1. Upload file or paste URL
# 2. Select OS (Windows 7/10/11, Linux)
# 3. Set analysis time (60-660 seconds)
# 4. Choose network simulation (residential proxy, Tor, custom)
# 5. Enable/disable: fake net, MITM proxy, HTTPS traffic capture
# 6. Run → watch in real-time → collect IOCs from results

# Free tier sandbox limits:
# - Windows 7 only (paid: Win 10/11, Linux)
# - 60-second timeout
# - Public submissions only (visible to community)
# - Limited to 3 concurrent tasks
```

### Correlating Sandbox Results with Engagement

```bash
# After sandbox analysis, correlate network IOCs with engagement logs
python3 << 'PYEOF'
import json

# Load sandbox IOCs (exported from ANY.RUN session)
with open('/workspace/ti/sandbox_iocs.json') as f:
    sandbox_iocs = json.load(f)

# Load engagement network logs
with open('/workspace/engagement/network_iocs.txt') as f:
    engagement_ips = set(line.strip() for line in f)

# Find overlap
sandbox_ips = set(sandbox_iocs.get('destinationIPs', []))
overlap = sandbox_ips & engagement_ips

if overlap:
    print(f"MATCH: {len(overlap)} IPs seen in both sandbox and engagement")
    for ip in sorted(overlap):
        print(f"  {ip}")
    print("\nThese IPs confirm the malware sample matches engagement activity")
else:
    print("No IP overlap — sample may be different variant or unrelated")
PYEOF
```

## Tools & Resources

| Resource | Purpose | URL |
|---|---|---|
| TI Lookup Web | Interactive IOC search | `https://intelligence.any.run/` |
| ANY.RUN Sandbox | Interactive malware analysis | `https://app.any.run/` |
| TI Lookup API | Programmatic IOC queries | `https://api.any.run/v1/intelligence/lookup` |
| Query Guide PDF | Official field reference | `https://intelligence.any.run/TI_Lookup_Query_Guide_v4.pdf` |
| anyrun-sdk (Python) | Python SDK for API integration | `pip install anyrun-sdk` |
| YARA Search | File hunting by YARA rule (shared quota) | `https://yara.any.run/` |
| TI Feeds | Automated IOC feeds (paid) | `https://any.run/threat-intelligence-feeds/` |

## Detection Signatures

These TI Lookup query patterns detect common attack behaviors:

| Query Pattern | Detects |
|---|---|
| `commandLine:"*powershell*-enc*"` | Base64-encoded PowerShell execution |
| `commandLine:"*wscript*//e:jscript*"` | WScript JScript execution |
| `filePath:"*\\Startup\\*.lnk"` | LNK-based persistence |
| `registryKey:"*\\Run\\*"` | Registry run key persistence |
| `suricataMessage:"ET TROJAN*"` | Suricata-flagged trojan traffic |
| `commandLine:"*certutil*-decode*"` | LOLBin file decode abuse |
| `destinationPort:"4444"` | Default Metasploit/Meterpreter port |
| `commandLine:"*schtasks*/create*"` | Scheduled task persistence |

## Error Handling & Edge Cases

| Problem | Cause | Solution |
|---|---|---|
| 0 results for known-malicious hash | Sample not submitted to ANY.RUN | Submit to sandbox first, then re-query after analysis completes |
| API returns 429 | Rate limit exceeded (free tier) | Wait and retry; batch queries with OR operator |
| API returns 401 | Invalid or expired API key | Regenerate key at `https://app.any.run/profile` |
| Partial results (10 sessions only) | Free tier limit | Results ordered by recency — most relevant for active campaigns |
| Wildcard query too broad | `domainName:"*"` matches everything | Narrow with additional field: `domainName:"*.evil.com" AND threatName:"Emotet"` |
| Registry key query fails | Single backslash not escaped | Always use double backslash: `registryKey:"HKCU\\Software\\..."` |
| Old samples missing | Sessions older than retention window | Supplement with VirusTotal/MalwareBazaar for historical coverage |
| Combined search returns nothing | AND too restrictive | Loosen by removing one condition; try individual fields first |

## Decision Gate

```
IF you have a file hash from a compromised host
  → Query sha256:"<HASH>" first — fastest path to malware family identification
IF you have a suspicious domain from DNS logs
  → Query domainName:"<DOMAIN>" — reveals which malware families use it
IF you have a C2 IP from network monitoring
  → Query destinationIP:"<IP>" — find all sandbox sessions that contacted it
IF TI Lookup returns 0 results
  → Submit the sample to ANY.RUN sandbox, then re-query after analysis
IF you need behavioral correlation (LOLBins, persistence)
  → Use commandLine/registryKey/filePath fields with wildcards
IF free tier quota exhausted
  → Fall back to VirusTotal, MalwareBazaar, or manual sandbox analysis
IF results need to go into engagement report
  → Export sandbox session as PDF; include session URL as evidence link
```
