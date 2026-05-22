---
name: osint
description: "Open-source intelligence gathering — email harvesting, social media profiling, breach data checking, employee enumeration, GitHub secret scanning, organizational mapping."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "OSINT, email harvest, employee enumeration, breach check, GitHub secrets, social media recon, Google dork, organizational mapping, theHarvester"
  tags: osint, email-harvest, employee-enum, github-secrets, breach-data, google-dork
  mitre_attack: T1589, T1593, T1597
---

# Open Source Intelligence (OSINT) Knowledge Base

OSINT collects publicly available information about targets without any direct interaction. This intelligence informs social engineering, credential attacks, and helps map the human attack surface alongside technical infrastructure.

## 1. Email Harvesting

### theHarvester
```bash
# Comprehensive email harvesting
theHarvester -d <target> -b all -l 500 -f theharvester_<target>.html

# Specific sources
theHarvester -d <target> -b google,bing,linkedin,twitter -l 200

# Output formats
theHarvester -d <target> -b all -f theharvester_<target> --screenshot screenshots/
```

### Manual Email Pattern Discovery
```bash
# Common email formats to test
# firstname.lastname@target.com
# firstnamelastname@target.com
# f.lastname@target.com
# firstname@target.com

# Verify email format via MX + SMTP (if in scope)
dig <target> MX +short
```

### Email Analysis Points
- **Naming convention**: Determines brute-force pattern for credential stuffing
- **Role-based emails**: security@, admin@, devops@ reveal team structure
- **Personal domains**: Cross-reference with social media for password patterns
- **Catch-all detection**: Some domains accept all addresses → harder to enumerate

## 2. Employee & Organization Enumeration

### LinkedIn Intelligence
- Search `site:linkedin.com/in "<target company>"` in Google
- Note: Direct LinkedIn scraping may violate ToS — use public search results
- Key data: Job titles, tech stack mentions, team sizes, recent hires

### Organizational Mapping
```
Target Corp
├── Engineering (mentions: Kubernetes, Go, React)
│   ├── Platform Team (AWS, Terraform)
│   ├── Backend Team (Python, FastAPI)
│   └── Frontend Team (React, TypeScript)
├── Security
│   └── SOC Team (Splunk, CrowdStrike mentioned)
├── DevOps/SRE
│   └── (Jenkins, ArgoCD, Datadog mentioned)
└── IT
    └── (Okta, Jamf mentioned in job posts)
```

### Tech Stack from Job Postings
```
Search job boards for:
"<target>" AND ("kubernetes" OR "terraform" OR "aws" OR "azure")
"<target>" AND ("react" OR "angular" OR "vue" OR "nextjs")
"<target>" AND ("python" OR "golang" OR "java" OR "rust")
```

## 3. GitHub & Code Repository OSINT

### Organization Discovery
```bash
# GitHub org search
curl -s "https://api.github.com/orgs/<target>/repos?per_page=100" | \
    python3 -c "import sys,json; [print(r['full_name'], r.get('description','')) for r in json.load(sys.stdin)]"

# Search for secrets in public repos
# Google dork approach
# site:github.com "<target>" password | secret | api_key | token
# site:github.com "<target>.com" filename:.env
```

### Secret Detection Patterns
```bash
# Using trufflehog (if available)
trufflehog github --org <target> --only-verified

# Using gitleaks (if available)
gitleaks detect --source /path/to/repo --report-path gitleaks_<target>.json

# Manual grep patterns in discovered repos
grep -rn "api[_-]key\|secret\|password\|token\|aws_access" --include="*.py" --include="*.js" --include="*.yaml" --include="*.env"
```

### Key Findings from Code Repos
- **Hardcoded credentials**: API keys, database passwords, AWS keys
- **Internal URLs**: staging/dev environments, internal APIs
- **Infrastructure as Code**: Terraform/CloudFormation files reveal architecture
- **CI/CD configs**: `.github/workflows/`, `Jenkinsfile` reveal deployment pipeline
- **Dependency files**: `package.json`, `requirements.txt` reveal tech stack

## 4. Domain & IP Intelligence

### Threat Intelligence
```bash
# VirusTotal domain report
curl -s "https://www.virustotal.com/api/v3/domains/<target>" \
    -H "x-apikey: <VT_API_KEY>" | python3 -m json.tool

# Shodan host info (if API key available)
curl -s "https://api.shodan.io/shodan/host/<IP>?key=<SHODAN_KEY>" | python3 -m json.tool

# AbuseIPDB check
curl -s "https://api.abuseipdb.com/api/v2/check?ipAddress=<IP>" \
    -H "Key: <ABUSE_KEY>" -H "Accept: application/json"
```

### Domain Reputation
- **VirusTotal**: Malware associations, passive DNS, URL scan history
- **Shodan/Censys**: Exposed services, historical banners, SSL certs
- **SecurityTrails**: Historical DNS records, IP history
- **URLScan.io**: Live page rendering, resource loading, redirects

### Wayback Machine
```bash
# Historical snapshots
curl -s "https://web.archive.org/cdx/search/cdx?url=*.example.com/*&output=text&fl=original&collapse=urlkey" | \
    sort -u > wayback_<target>.txt

# Look for old admin panels, login pages, API docs
grep -iE "(admin|login|api|swagger|debug|config)" wayback_<target>.txt
```

## 5. Breach & Credential Data

### Approach (Ethical Boundaries)
- Check **Have I Been Pwned** API for breach exposure (with authorization)
- Document which breaches may contain target employee credentials
- **Never** access or download actual breach databases without explicit authorization
- Focus on: Which breaches? What data types exposed? Credential reuse risk?

### HIBP API Check
```bash
# Check domain breach status (requires API key)
curl -s "https://haveibeenpwned.com/api/v3/breaches" \
    -H "hibp-api-key: <KEY>" | python3 -c "
import sys, json
for b in json.load(sys.stdin):
    if '<target>' in b.get('Domain','').lower():
        print(f\"{b['Name']}: {b['BreachDate']} - {b['PwnCount']:,} records\")
        print(f\"  Data: {', '.join(b['DataClasses'])}\")"
```

### Credential Intelligence (What to Document)
- Number of breaches involving target domain
- Types of data exposed (passwords, hashes, emails, PII)
- Breach dates (recent = higher risk of valid credentials)
- Password reuse likelihood across services

## 6. Social Media Intelligence

### Platform-Specific Searches
```
Twitter/X: from:<target_handle> | "@<target>" filter:links
Reddit: site:reddit.com "<target company>"
Glassdoor: Company reviews reveal internal culture, tech stack, complaints
Crunchbase: Funding, acquisitions, key personnel
```

### Metadata from Social Media
- **Photos**: EXIF data (GPS coordinates, device info, timestamps)
- **Documents**: PDF metadata (author names, software versions, internal paths)
- **Posts**: Technology mentions, frustration with tools (vulnerability hints)

## 7. Google Dorking (Advanced)

### Target-Specific Dorks
```
# Exposed documents
site:<target> filetype:pdf | filetype:doc | filetype:xls
site:<target> filetype:sql | filetype:bak | filetype:log

# Admin/config exposure
site:<target> inurl:admin | inurl:login | inurl:dashboard
site:<target> intitle:"index of" | intitle:"directory listing"

# Error messages / debug info
site:<target> "error" | "exception" | "stack trace" | "debug"
site:<target> "not for distribution" | "confidential" | "internal use only"

# Third-party integrations
"<target>.com" site:trello.com | site:notion.so | site:pastebin.com
"<target>.com" site:stackoverflow.com "api" | "key" | "secret"
```

## 8. Workflow: OSINT Sequence

1. **Email Harvesting** → theHarvester, manual pattern discovery
2. **Employee Enumeration** → LinkedIn, job postings, org chart mapping
3. **Code Repository Search** → GitHub org, secret scanning, IaC review
4. **Domain Intelligence** → VirusTotal, Shodan, SecurityTrails
5. **Breach Assessment** → HIBP, breach database scope
6. **Social Media** → Platform searches, metadata extraction
7. **Google Dorking** → Advanced searches for exposed data
8. **Wayback Machine** → Historical URL analysis
9. **Synthesis** → Combine with technical recon, build target profile

## 9. Output Files
```
./
├── theharvester_<target>.html     # Email harvesting results
├── emails_<target>.txt            # Cleaned email list
├── org_chart_<target>.md          # Organizational mapping
├── github_secrets_<target>.txt    # Code repo findings
├── wayback_<target>.txt           # Historical URLs
├── breach_assessment_<target>.md  # Breach exposure summary
└── osint_<target>_summary.md      # Consolidated OSINT report
```

## 10. Ethical Boundaries

- **Always passive**: OSINT must not involve direct target interaction
- **Public data only**: Only use information available in public sources
- **No impersonation**: Do not create fake accounts or social engineer employees
- **Breach data**: Document exposure risk, never access raw breach dumps without authorization
- **Privacy**: Report findings that are security-relevant, not personal embarrassments
