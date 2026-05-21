# DNS Reconnaissance Techniques — Deep Reference

## DNS Record Types for Recon

| Record | Command | Intel Value |
|--------|---------|-------------|
| A/AAAA | `dig A <TARGET>` | IP addresses, hosting provider |
| MX | `dig MX <TARGET>` | Mail infrastructure, cloud provider |
| NS | `dig NS <TARGET>` | DNS hosting, delegation chain |
| TXT | `dig TXT <TARGET>` | SPF, DKIM, DMARC, domain verification tokens |
| CNAME | `dig CNAME sub.<TARGET>` | CDN, cloud services, takeover candidates |
| SOA | `dig SOA <TARGET>` | Primary DNS, admin email, zone serial |
| SRV | `dig SRV _sip._tcp.<TARGET>` | Service endpoints (SIP, LDAP, Kerberos) |
| PTR | `dig -x <IP>` | Reverse DNS, shared hosting discovery |
| AXFR | `dig AXFR <TARGET> @<NS>` | Full zone transfer (rarely successful) |

## Subdomain Enumeration Tool Comparison

| Tool | Method | Speed | Coverage | Best For |
|------|--------|-------|----------|----------|
| subfinder | Passive (APIs) | Fast | High | First pass, API-powered enum |
| amass enum -passive | Passive (multi-source) | Medium | Very High | Comprehensive passive |
| amass enum -active | Active + passive | Slow | Maximum | Thorough enum with DNS brute |
| assetfinder | Passive | Very Fast | Medium | Quick initial discovery |
| findomain | Passive | Fast | Medium | CI/CD integration |

## Subfinder Configuration

```yaml
# ~/.config/subfinder/provider-config.yaml
securitytrails: [API_KEY]
shodan: [API_KEY]
censys: [API_KEY:SECRET]
virustotal: [API_KEY]
chaos: [API_KEY]
github: [TOKEN1, TOKEN2]  # Multiple tokens for rate limits
```

## Certificate Transparency Deep Dive

### Sources
| Source | URL | Notes |
|--------|-----|-------|
| crt.sh | `https://crt.sh/?q=%.<TARGET>&output=json` | Comodo CT log aggregator |
| Censys | API | Requires API key, best coverage |
| Google CT | transparencyreport.google.com | Browser-integrated |
| Facebook CT | ct.fb.com | Large CT log |

### crt.sh Advanced Queries
```bash
# All subdomains (including expired certs)
curl -s "https://crt.sh/?q=%25.<TARGET>&output=json" | jq -r '.[].name_value' | sort -u

# Only valid/current certs
curl -s "https://crt.sh/?q=%25.<TARGET>&output=json" | jq -r 'select(.not_after > now) | .name_value' | sort -u

# Organization search
curl -s "https://crt.sh/?o=<ORG_NAME>&output=json" | jq -r '.[].common_name' | sort -u
```

## Passive DNS Databases

| Service | Coverage | Access |
|---------|----------|--------|
| SecurityTrails | Historical DNS + WHOIS | API (free tier) |
| VirusTotal | DNS resolutions | API |
| RiskIQ/PassiveTotal | Historical DNS pairs | API (commercial) |
| DNSDB (Farsight) | Largest passive DNS | API (commercial) |
| Shodan | InternetDB, DNS data | API |

## ASN/BGP Intelligence

```bash
# Find ASN for IP
whois -h whois.cymru.com " -v <IP>"

# Find all prefixes for ASN
whois -h whois.radb.net -- "-i origin AS<NUMBER>" | grep "^route:"

# BGP toolkit
curl -s "https://api.bgpview.io/asn/<NUMBER>/prefixes" | jq '.data.ipv4_prefixes[].prefix'

# Map org to ASN
curl -s "https://api.bgpview.io/search?query_term=<ORG>" | jq '.data.asns[]'
```

## Tool Chaining Pattern

```bash
# Full passive recon pipeline for <TARGET>
subfinder -d <TARGET> -all -silent | \
  httpx -silent -sc -td -title -ip | \
  tee recon/passive_results.txt

# DNS + subdomain + live host validation
subfinder -d <TARGET> -silent > recon/subs.txt
cat recon/subs.txt | dnsx -silent -a -resp | tee recon/dns_resolved.txt
cat recon/subs.txt | httpx -silent -sc -td -title | tee recon/live_hosts.txt
```
