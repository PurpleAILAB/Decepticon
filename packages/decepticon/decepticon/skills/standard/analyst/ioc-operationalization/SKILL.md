---
name: ioc-operationalization
description: "Operationalize Indicators of Compromise from engagement findings — ingest IOCs into blocking infrastructure (firewalls, EDR, DNS sinkholes, proxy), build automated feed pipelines, age-out stale indicators, and validate enforcement effectiveness."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "ioc blocking, operationalize ioc, blocklist, firewall block, edr block, dns sinkhole, threat feed, ioc feed, ioc pipeline, block indicators, ioc ingestion, ioc enforcement, stix feed ingest"
  tags: "ioc, operationalization, blocking, firewall, edr, dns-sinkhole, threat-feed, automation, enforcement"
  mitre_attack: "M1031, M1037, M1050"
---

# IOC Operationalization

Take Indicators of Compromise from engagement findings, threat intelligence feeds, and the `ti-ioc-extraction` skill and push them into blocking/detection infrastructure. This skill covers the full lifecycle: extraction → validation → ingestion → enforcement → age-out.

## Quick Reference

```bash
# Load extracted IOCs (output of ti-ioc-extraction skill)
cat /workspace/iocs/deduped.json | python3 -c "
import json, sys
iocs = json.load(sys.stdin)
for cat, items in iocs.items():
    print(f'{cat}: {len(items)} indicators')
"

# Quick CSV export for firewall import
python3 << 'PYEOF'
import json, csv

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

with open('/workspace/iocs/firewall_blocklist.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['type', 'indicator', 'action', 'comment'])
    for ip in iocs.get('ipv4s', []):
        writer.writerow(['ipv4', ip, 'block', 'engagement-finding'])
    for domain in iocs.get('domains', []):
        writer.writerow(['domain', domain, 'block', 'engagement-finding'])

print("[+] Blocklist exported → /workspace/iocs/firewall_blocklist.csv")
PYEOF
```

## MITRE ATT&CK Mitigations

| Mitigation | ID | IOC Type |
|---|---|---|
| Network Intrusion Prevention | M1031 | IP addresses, domains, URLs |
| Network Segmentation | M1037 | C2 infrastructure IPs |
| Exploit Protection | M1050 | File hashes (block execution) |

## 1. IOC Validation Before Deployment

Never push raw IOCs into blocking infrastructure without validation. False positives in blocklists cause outages.

```bash
# Validate IPs — ensure they're not internal, CDN, or major cloud providers
python3 << 'PYEOF'
import json, ipaddress

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

SAFE_RANGES = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
]

MAJOR_PROVIDERS = {
    '8.8.8.8', '8.8.4.4',           # Google DNS
    '1.1.1.1', '1.0.0.1',           # Cloudflare DNS
    '208.67.222.222', '208.67.220.220',  # OpenDNS
}

validated = []
rejected = []

for ip_str in iocs.get('ipv4s', []):
    ip = ipaddress.ip_address(ip_str)
    if ip_str in MAJOR_PROVIDERS:
        rejected.append((ip_str, 'major_provider'))
    elif any(ip in net for net in SAFE_RANGES):
        rejected.append((ip_str, 'private_range'))
    else:
        validated.append(ip_str)

with open('/workspace/iocs/validated_ips.json', 'w') as f:
    json.dump({'validated': validated, 'rejected': rejected}, f, indent=2)

print(f"[+] Validated: {len(validated)} IPs | Rejected: {len(rejected)} IPs")
for ip, reason in rejected:
    print(f"    SKIP {ip} ({reason})")
PYEOF

# Validate domains — check against Alexa/Tranco top 10K
python3 << 'PYEOF'
import json

# Load Tranco top 10K (download once: curl -sL https://tranco-list.eu/top-1m.csv.zip | ...)
try:
    with open('/workspace/reference/tranco_top10k.txt') as f:
        top_domains = set(line.strip().lower() for line in f)
except FileNotFoundError:
    top_domains = set()
    print("[!] No Tranco list found — skipping popularity filter")

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

validated = []
rejected = []
for domain in iocs.get('domains', []):
    if domain.lower() in top_domains:
        rejected.append((domain, 'top_10k_domain'))
    else:
        validated.append(domain)

with open('/workspace/iocs/validated_domains.json', 'w') as f:
    json.dump({'validated': validated, 'rejected': rejected}, f, indent=2)

print(f"[+] Validated: {len(validated)} domains | Rejected: {len(rejected)} domains")
PYEOF
```

## 2. Firewall / Network Blocking

### Palo Alto NGFW

```bash
# Generate External Dynamic List (EDL) format for Palo Alto
python3 << 'PYEOF'
import json

with open('/workspace/iocs/validated_ips.json') as f:
    data = json.load(f)

# IP EDL — one IP per line
with open('/workspace/iocs/edl_ips.txt', 'w') as f:
    for ip in data['validated']:
        f.write(f"{ip}\n")

print(f"[+] EDL IP list → /workspace/iocs/edl_ips.txt ({len(data['validated'])} entries)")
PYEOF

# Host on a web server the NGFW can poll:
# Objects → External Dynamic Lists → New → Type: IP List
# Source: https://ti-server.internal/feeds/edl_ips.txt
# Refresh: every 5 minutes
# → Apply to Security Policy: Block rule
```

### iptables / nftables (Linux)

```bash
# Generate iptables rules
while IFS= read -r ip; do
  echo "iptables -A INPUT -s $ip -j DROP"
  echo "iptables -A OUTPUT -d $ip -j DROP"
done < /workspace/iocs/edl_ips.txt > /workspace/iocs/iptables_rules.sh

# nftables set
echo "define blocked_ips = {" > /workspace/iocs/nftables_set.conf
paste -sd',' /workspace/iocs/edl_ips.txt >> /workspace/iocs/nftables_set.conf
echo "}" >> /workspace/iocs/nftables_set.conf
```

## 3. EDR Blocking (Hash-Based)

### CrowdStrike Falcon

```bash
# Upload IOCs via Falcon API
python3 << 'PYEOF'
import json, requests, os

FALCON_CLIENT_ID = os.environ.get('FALCON_CLIENT_ID', '<CLIENT_ID>')
FALCON_SECRET = os.environ.get('FALCON_CLIENT_SECRET', '<SECRET>')
FALCON_BASE = 'https://api.crowdstrike.com'

# Authenticate
auth = requests.post(f'{FALCON_BASE}/oauth2/token', data={
    'client_id': FALCON_CLIENT_ID,
    'client_secret': FALCON_SECRET
})
token = auth.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

indicators = []
for h in iocs.get('sha256s', []):
    indicators.append({
        'type': 'sha256',
        'value': h,
        'action': 'prevent',
        'severity': 'high',
        'description': 'Engagement finding — malicious hash',
        'platforms': ['windows', 'linux', 'mac'],
        'applied_globally': True
    })

if indicators:
    resp = requests.post(f'{FALCON_BASE}/iocs/entities/indicators/v1',
        headers=headers, json={'indicators': indicators})
    print(f"[+] Uploaded {len(indicators)} hash IOCs to Falcon: {resp.status_code}")
PYEOF
```

### Microsoft Defender for Endpoint

```bash
# Upload via MDE TI API
python3 << 'PYEOF'
import json, requests, os

TENANT_ID = os.environ.get('AZURE_TENANT_ID', '<TENANT>')
CLIENT_ID = os.environ.get('AZURE_CLIENT_ID', '<CLIENT>')
CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET', '<SECRET>')

# Get token
auth = requests.post(f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token', data={
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'scope': 'https://api.securitycenter.microsoft.com/.default',
    'grant_type': 'client_credentials'
})
token = auth.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

with open('/workspace/iocs/deduped.json') as f:
    iocs = json.load(f)

for h in iocs.get('sha256s', []):
    indicator = {
        'indicatorValue': h,
        'indicatorType': 'FileSha256',
        'action': 'AlertAndBlock',
        'title': 'Engagement Finding',
        'severity': 'High',
        'description': 'Malicious file hash from engagement',
        'generateAlert': True
    }
    resp = requests.post(
        'https://api.securitycenter.microsoft.com/api/indicators',
        headers=headers, json=indicator)
    print(f"    {h[:16]}… → {resp.status_code}")
PYEOF
```

## 4. DNS Sinkholing

```bash
# Generate RPZ (Response Policy Zone) entries
python3 << 'PYEOF'
import json

with open('/workspace/iocs/validated_domains.json') as f:
    data = json.load(f)

SINKHOLE_IP = '127.0.0.1'  # Or internal sinkhole server

with open('/workspace/iocs/rpz_zone.txt', 'w') as f:
    f.write('; RPZ zone file — generated from engagement IOCs\n')
    f.write('$TTL 300\n')
    for domain in data['validated']:
        f.write(f'{domain} CNAME .\n')              # NXDOMAIN response
        f.write(f'*.{domain} CNAME .\n')             # Wildcard subdomain block

print(f"[+] RPZ zone → /workspace/iocs/rpz_zone.txt ({len(data['validated'])} domains)")
PYEOF

# Pi-hole / AdGuard blocklist format
python3 -c "
import json
with open('/workspace/iocs/validated_domains.json') as f:
    for d in json.load(f)['validated']:
        print(f'0.0.0.0 {d}')
" > /workspace/iocs/hosts_blocklist.txt
```

## 5. Automated Feed Pipeline

```bash
# STIX/TAXII feed ingestion pipeline
python3 << 'PYEOF'
import json, os
from datetime import datetime, timedelta, timezone

FEED_DIR = '/workspace/feeds'
IOC_DIR = '/workspace/iocs'
MAX_AGE_DAYS = 90

os.makedirs(FEED_DIR, exist_ok=True)

def age_out_indicators(ioc_file: str, max_age_days: int) -> dict:
    """Remove indicators older than max_age_days."""
    with open(ioc_file) as f:
        data = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    active = []
    expired = []

    for indicator in data.get('indicators', []):
        added = datetime.fromisoformat(indicator.get('added', '2000-01-01'))
        if added.replace(tzinfo=timezone.utc) > cutoff:
            active.append(indicator)
        else:
            expired.append(indicator)

    return {'active': active, 'expired': expired}

def merge_feeds(existing_file: str, new_iocs: dict) -> None:
    """Merge new IOCs into existing feed, deduplicating by value."""
    try:
        with open(existing_file) as f:
            existing = json.load(f)
    except FileNotFoundError:
        existing = {'indicators': []}

    seen = {i['value'] for i in existing['indicators']}
    added = 0
    for cat, items in new_iocs.items():
        for item in items:
            if item not in seen:
                existing['indicators'].append({
                    'type': cat,
                    'value': item,
                    'added': datetime.now(timezone.utc).isoformat(),
                    'source': 'engagement'
                })
                seen.add(item)
                added += 1

    with open(existing_file, 'w') as f:
        json.dump(existing, f, indent=2)

    print(f"[+] Merged {added} new indicators into {existing_file}")

# Run pipeline
with open(f'{IOC_DIR}/deduped.json') as f:
    new_iocs = json.load(f)

merge_feeds(f'{FEED_DIR}/master_feed.json', new_iocs)

result = age_out_indicators(f'{FEED_DIR}/master_feed.json', MAX_AGE_DAYS)
print(f"[+] Active: {len(result['active'])} | Expired: {len(result['expired'])}")
PYEOF
```

## 6. Enforcement Validation

```bash
# Test that blocked IPs are actually unreachable
python3 << 'PYEOF'
import json, subprocess

with open('/workspace/iocs/validated_ips.json') as f:
    ips = json.load(f)['validated'][:10]  # Sample first 10

for ip in ips:
    result = subprocess.run(
        ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
         '--connect-timeout', '5', f'http://{ip}/'],
        capture_output=True, text=True, timeout=10
    )
    status = result.stdout.strip()
    blocked = status == '000' or result.returncode != 0
    print(f"  {ip}: {'BLOCKED ✓' if blocked else f'REACHABLE ({status}) ✗'}")
PYEOF

# Verify DNS sinkhole resolution
python3 << 'PYEOF'
import json, subprocess

with open('/workspace/iocs/validated_domains.json') as f:
    domains = json.load(f)['validated'][:10]

for domain in domains:
    result = subprocess.run(
        ['nslookup', domain], capture_output=True, text=True, timeout=10
    )
    if '127.0.0.1' in result.stdout or 'NXDOMAIN' in result.stdout:
        print(f"  {domain}: SINKHOLED ✓")
    else:
        print(f"  {domain}: NOT SINKHOLED ✗")
PYEOF
```

## 7. IOC Lifecycle Management

| Phase | Action | Frequency |
|---|---|---|
| **Ingest** | Extract from findings, validate, deduplicate | Per engagement |
| **Deploy** | Push to firewalls, EDR, DNS, proxy | Within 4 hours of validation |
| **Monitor** | Verify enforcement, check for hits | Daily |
| **Age-out** | Remove indicators older than 90 days | Weekly automated |
| **Review** | Audit false positive reports, adjust | Monthly |

## References

- MITRE ATT&CK Mitigations — https://attack.mitre.org/mitigations/
- Palo Alto External Dynamic Lists — https://docs.paloaltonetworks.com/pan-os/11-0/pan-os-admin/policy/use-an-external-dynamic-list-in-policy
- CrowdStrike IOC API — https://falcon.crowdstrike.com/documentation/
- DNS RPZ — https://dnsrpz.info/
