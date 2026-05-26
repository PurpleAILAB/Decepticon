---
name: passive-recon
description: "Passive intelligence gathering without touching the target — DNS, WHOIS, subdomain enumeration, Certificate Transparency, technology fingerprinting, ASN mapping."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "passive recon, WHOIS, DNS lookup, subdomain, subfinder, amass, crt.sh, certificate transparency, ASN, httpx, tech fingerprint"
  tags: passive, dns, subdomain-enum, whois, ct-logs, httpx, asn
  mitre_attack: T1590, T1591, T1592, T1593, T1596
---

# Passive Reconnaissance Knowledge Base

Passive reconnaissance gathers intelligence **without directly interacting with the target's systems**. This leaves no logs, no alerts, and no fingerprints on the target. Always exhaust passive methods before transitioning to active techniques.

## Quick Reference — Copy-Paste Commands
```bash
# Full passive workflow for <TARGET>
whois <TARGET>
dig <TARGET> ANY +noall +answer
subfinder -d <TARGET> -o subdomains.txt
amass enum -passive -d <TARGET> -o amass_subs.txt
curl -s "https://crt.sh/?q=%25.<TARGET>&output=json" | python3 -c "import sys,json; [print(x['name_value']) for x in json.load(sys.stdin)]" | sort -u
httpx -l subdomains.txt -sc -cl -ct -title -tech-detect -o httpx_<TARGET>.txt
curl -sI https://<TARGET>
```

## 1. WHOIS Intelligence

### Domain WHOIS
```bash
whois example.com
```
**Extract:** Registrar, creation/expiration dates, nameservers, registrant organization, abuse contacts.

### IP WHOIS (ASN Mapping)
```bash
whois -h whois.radb.net -- '-i origin AS12345'
whois <IP_ADDRESS>
```
**Extract:** ASN ownership, IP ranges allocated, network name, organization.

### BGP/ASN Enumeration
```bash
# ASN lookup via Team Cymru
whois -h whois.cymru.com " -v <IP_ADDRESS>"

# All prefixes for an ASN
whois -h whois.radb.net -- '-i origin AS12345' | grep route

# Using amass for ASN intelligence
amass intel -asn <ASN_NUMBER>
```

### Key Analysis Points
- **Registrar patterns**: Same registrar across multiple domains may indicate shared ownership
- **Nameserver clustering**: Shared NS records reveal infrastructure relationships
- **Registration dates**: Recently registered domains may indicate campaign infrastructure
- **Privacy protection**: WHOIS privacy services indicate security awareness
- **ASN ownership**: Map all IP ranges belonging to the target organization

## 2. DNS Reconnaissance

### Comprehensive Record Queries
```bash
# All record types
dig example.com ANY +noall +answer

# Specific records
dig example.com A +short
dig example.com AAAA +short
dig example.com MX +short
dig example.com NS +short
dig example.com TXT +short
dig example.com CNAME +short
dig example.com SOA +short

# Reverse DNS
dig -x <IP_ADDRESS> +short
```

### DNS Zone Transfer Attempt
```bash
# Enumerate nameservers first
dig example.com NS +short

# Attempt zone transfer (AXFR)
dig @ns1.example.com example.com AXFR
```
**Note:** Zone transfers are a grey area — they are a DNS protocol feature but unauthorized transfers may violate ROE. Confirm scope before attempting.

### DNS Analysis Patterns
- **MX records**: Reveal email infrastructure (Google Workspace, Microsoft 365, self-hosted)
- **TXT records**: SPF, DKIM, DMARC reveal email security posture; may contain verification tokens leaking service usage
- **NS delegation**: Identifies DNS hosting provider (Cloudflare, AWS Route53, etc.)
- **CNAME chains**: Expose CDN usage, third-party service integrations, potential subdomain takeover candidates
- **SOA records**: Reveal primary DNS admin, serial numbers (change frequency indicator)
- **CAA records**: Certificate Authority Authorization — reveals which CAs can issue certs

## 3. Subdomain Enumeration

### subfinder (Primary Tool)
```bash
# Basic enumeration
subfinder -d example.com -silent

# Save to file for large results
subfinder -d example.com -o subdomains.txt

# Multiple sources with verbose
subfinder -d example.com -all -v

# Recursive enumeration
subfinder -d example.com -recursive
```

### amass (Comprehensive)
```bash
# Passive-only enumeration (no DNS brute force)
amass enum -passive -d example.com -o amass_subs.txt

# With additional intelligence sources
amass enum -passive -d example.com -src -ip

# Intel mode — discover root domains from ASN/org
amass intel -org "Target Corp"
amass intel -asn 12345 -whois -d example.com
```

### DNS Brute Force (Secondary)
```bash
# Using a wordlist if available
for sub in $(cat /usr/share/wordlists/subdomains.txt); do
    dig +short "$sub.example.com" | grep -v "^$" && echo "$sub.example.com"
done
```

### Subdomain Analysis
- **Naming patterns**: `dev.`, `staging.`, `test.`, `admin.`, `vpn.`, `mail.` reveal internal structure
- **IP clustering**: Group subdomains by IP to identify shared hosting / infrastructure segments
- **Cloud indicators**: `*.amazonaws.com`, `*.azurewebsites.net` CNAME targets reveal cloud usage
- **Dangling CNAMEs**: Subdomains pointing to deprovisioned services = potential subdomain takeover

## 4. Certificate Transparency (CT) Logs

### Using crt.sh
```bash
curl -s "https://crt.sh/?q=%25.example.com&output=json" | \
    python3 -c "import sys,json; [print(x['name_value']) for x in json.load(sys.stdin)]" | \
    sort -u
```

### Analysis Value
- CT logs are a **public, immutable** record of all TLS certificates issued
- Reveals subdomains not found by DNS enumeration
- Shows historical certificates — even revoked ones expose past infrastructure
- Wildcard certificates (`*.example.com`) indicate broad subdomain usage

## 5. Web Fingerprinting (Passive)

### HTTP Headers Analysis
```bash
curl -sI https://example.com
```
**Look for:**
- `Server`: Web server software and version
- `X-Powered-By`: Backend framework
- `X-CDN`, `CF-RAY`: CDN identification
- `Strict-Transport-Security`: HSTS configuration
- `Content-Security-Policy`: CSP reveals allowed domains / integrations

### httpx — Bulk Probing & Tech Detection
```bash
# Probe all subdomains with tech detection
httpx -l subdomains.txt -sc -cl -ct -title -tech-detect -o httpx_results.txt

# Filter live hosts with specific status codes
httpx -l subdomains.txt -mc 200,301,302,403 -title -tech-detect

# JSON output for parsing
httpx -l subdomains.txt -sc -title -tech-detect -json -o httpx.json
```
**httpx is critical for:**
- Validating which subdomains are actually alive (HTTP response)
- Bulk technology fingerprinting (frameworks, CDN, WAF)
- Status code and content-length triage

### Technology Stack Detection
```bash
curl -s https://example.com | grep -Ei '(wp-content|drupal|joomla|next|react|angular|vue)'
```

## 6. Tool Chaining & Output Normalization

### Piping Between Tools
```bash
# subfinder → httpx → nuclei pipeline
subfinder -d <TARGET> -silent | httpx -silent -sc -title -tech-detect | tee live_<TARGET>.txt
cat live_<TARGET>.txt | awk '{print $1}' | nuclei -severity critical,high -silent

# CT logs → dedup → resolve
curl -s "https://crt.sh/?q=%25.<TARGET>&output=json" | \
  python3 -c "import sys,json; [print(x['name_value']) for x in json.load(sys.stdin)]" | \
  sort -u | httpx -silent -o ct_live_<TARGET>.txt

# amass + subfinder → merge → dedup
cat amass_subs.txt subdomains.txt | sort -u > all_subs_<TARGET>.txt
```

### Output Normalization
Normalize all subdomain sources into a single format for downstream tools:
```bash
# Standard format: one subdomain per line, no protocol, no trailing dot
cat all_subs_<TARGET>.txt | \
  sed 's|https\?://||; s|/.*||; s|\.$||' | \
  tr '[:upper:]' '[:lower:]' | sort -u > normalized_subs_<TARGET>.txt
```

## 7. Passive DNS & Historical Analysis

### Passive DNS Sources
```bash
# SecurityTrails API (if available)
curl -s "https://api.securitytrails.com/v1/domain/<TARGET>/subdomains" \
  -H "APIKEY: $ST_KEY" | python3 -m json.tool

# VirusTotal passive DNS
curl -s "https://www.virustotal.com/api/v3/domains/<TARGET>/resolutions?limit=40" \
  -H "x-apikey: $VT_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('data', []):
  attrs = r['attributes']
  print(f\"{attrs.get('date','?')}  {attrs.get('host_name','?')} -> {attrs.get('ip_address','?')}\")
"
```

### Historical DNS Value
- **IP changes** reveal infrastructure migrations (on-prem → cloud)
- **Old A records** may still resolve to accessible legacy servers
- **Expired CNAME targets** are subdomain takeover candidates
- **MX history** shows email provider changes

## 8. OSINT Handoff

> **Boundary**: Passive recon covers **technical infrastructure** (DNS, subdomains, WHOIS, ASN, CT logs, web fingerprinting). For **human and organizational intelligence** (email harvesting, employee enumeration, GitHub secret scanning, breach data, social media, Google dorking, Wayback Machine), use the dedicated `osint` skill.

After completing passive recon, hand off discovered domains and infrastructure data to the `osint` skill for:
- Email pattern discovery from discovered domains
- Employee and org structure enumeration
- GitHub/GitLab secret scanning for discovered organizations
- Breach exposure assessment for discovered email domains
- Google dorking using discovered subdomains and paths
- Wayback Machine analysis of discovered URLs

## 9. Error Handling & Edge Cases

### When Tools Fail
| Problem | Cause | Solution |
|---------|-------|----------|
| subfinder returns 0 results | API keys not configured | Run with `-all` flag; add API keys to `~/.config/subfinder/provider-config.yaml` |
| crt.sh timeout | Rate limiting | Wait 30s and retry; use local CT log mirror if available |
| httpx hangs on large list | Too many concurrent requests | Add `-threads 25 -timeout 5` |
| amass very slow | Default config too aggressive | Use `-passive` flag only; set timeout with `-timeout 10` |
| WHOIS blocked | Rate limited by registrar | Try alternative WHOIS server: `whois -h whois.verisign-grs.com <TARGET>` |

### False Positive Reduction
- **Wildcard DNS**: Check if `*.TARGET` resolves → if yes, filter out wildcard IPs from subdomain results
- **Parking pages**: httpx title containing "parked", "coming soon", "default" → deprioritize
- **CDN IPs**: Multiple subdomains resolving to same CDN IP ≠ same server

```bash
# Detect wildcard DNS
WILDCARD_IP=$(dig +short nonexistent-random-string.<TARGET>)
if [ -n "$WILDCARD_IP" ]; then
  echo "WILDCARD detected: $WILDCARD_IP — filtering results"
  grep -v "$WILDCARD_IP" resolved_subs.txt > filtered_subs.txt
fi
```

## 10. Workflow: Passive Recon Sequence

1. **WHOIS + ASN** → Establish ownership, registrar, nameservers, IP ranges
2. **DNS Records** → Map A, MX, NS, TXT, SOA, CAA records
3. **Subdomain Enumeration** → subfinder + amass + CT logs
4. **Deduplicate & Normalize** → Merge all sources, remove wildcards
5. **Live Host Probing** → httpx on all discovered subdomains
6. **Passive DNS History** → Check for old IPs, infrastructure changes
7. **Web Fingerprinting** → Technology stack on key assets
8. **→ Hand off to `osint` skill** → Email, employee, GitHub, breach, social media, dorking
9. **Synthesis** → Build infrastructure map, identify high-value targets for active phase

## 11. Decision Gate: Passive → Active Transition

Before moving to active reconnaissance, you must have:
- [ ] Complete domain/subdomain inventory (deduplicated, wildcard-filtered)
- [ ] DNS infrastructure map (nameservers, mail servers, CDN)
- [ ] IP address grouping and ASN mapping
- [ ] Live host validation (httpx results)
- [ ] Technology stack indicators
- [ ] Passive DNS history reviewed
- [ ] OSINT findings documented
- [ ] Identified high-value targets that justify active probing

## Bundled Resources

### References
- `references/dns-techniques.md` — DNS record types, subdomain tool comparison, CT deep dive, ASN/BGP intel, passive DNS databases. Read when you need detailed technique reference beyond this skill's quick-reference commands.

### Scripts
- `scripts/parse_subdomains.py` — Parse and deduplicate subdomain results from multiple tools. Usage: `python scripts/parse_subdomains.py recon/*.txt -d <TARGET> -o recon/all_subs.txt`
