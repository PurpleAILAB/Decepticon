---
name: active-recon
description: "Active target probing — port scanning, service detection, vulnerability scanning, banner grabbing, web directory fuzzing, SSL/TLS analysis."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "port scan, nmap, active scan, service detection, banner grab, vulnerability scan, nuclei, nikto, SSL analysis, network sweep, testssl"
  tags: nmap, port-scan, service-detection, banner-grab, nuclei, vulnerability-scan
  mitre_attack: T1595, T1595.001, T1595.002, T1595.003
---

# Active Reconnaissance Knowledge Base

Active reconnaissance **directly interacts with target systems**. Every packet sent may be logged, detected, or trigger alerts. Use active techniques only after passive reconnaissance has identified specific targets that warrant further investigation.

## Quick Reference — Common Scan Patterns
```bash
# Stealth SYN scan with version detection (recommended starting point)
nmap -sS -sV -p 22,80,443,8080,8443 <TARGET> -oN nmap_<TARGET>.txt -oX nmap_<TARGET>.xml

# Full top-1000 port scan
nmap -sS -sV --top-ports 1000 -T2 <TARGET> -oN nmap_full_<TARGET>.txt

# Script enumeration on discovered ports
nmap -sC -sV -p <PORTS> <TARGET> -oN nmap_scripts_<TARGET>.txt

# UDP scan (DNS, SNMP, NTP)
nmap -sU -p 53,161,123 <TARGET> -oN nmap_udp_<TARGET>.txt

# Web directory fuzzing
ffuf -u https://<TARGET>/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,301,302,403 -o ffuf_<TARGET>.json

# Vulnerability scan
nuclei -u https://<TARGET> -severity critical,high -o nuclei_<TARGET>.txt
```

## 1. OPSEC Principles for Active Scanning

### Detection Avoidance
- **Never scan entire ranges blindly** — target specific IPs/ports identified during passive recon
- **Rate limiting**: Slow scans blend with normal traffic; fast scans trigger IDS/IPS
- **Timing**: Scan during business hours when traffic volume provides cover
- **Source management**: Be aware your sandbox IP is the scan origin
- **User-Agent rotation**: Vary HTTP user agents for web scanning tools

### Scan Justification
Before every active scan, document:
1. **What** you're scanning and **why**
2. **What passive intel** led to this decision
3. **Expected noise level** and detection risk

## 2. Port Scanning with Nmap

### Stealth SYN Scan (Default for Recon)
```bash
# Targeted port scan — specific ports from passive findings
nmap -sS -p 22,80,443,8080,8443 <target_ip>

# Top 1000 ports with service detection
nmap -sS -sV --top-ports 1000 <target_ip>

# Full 65535 port scan (slow, use only when justified)
nmap -sS -p- --min-rate 1000 <target_ip>

# Save results
nmap -sS -sV -p 22,80,443 <target_ip> -oN nmap_scan.txt -oX nmap_scan.xml
```

### Service Version Detection
```bash
# Version detection on specific ports
nmap -sV --version-intensity 5 -p 22,80,443 <target_ip>

# Aggressive version + OS detection
nmap -sV -O -p 22,80,443 <target_ip>

# Script-based enumeration
nmap -sC -sV -p 22,80,443 <target_ip>
```

### Scan Types Reference

| Flag | Scan Type | Noise Level | Use Case |
|------|-----------|-------------|----------|
| `-sS` | SYN (half-open) | Low | Default stealth scan |
| `-sT` | TCP Connect | Medium | When SYN scan unavailable |
| `-sU` | UDP | Medium-High | DNS (53), SNMP (161), NTP (123) |
| `-sV` | Version detect | Medium | Service identification |
| `-sC` | Default scripts | Medium-High | Common vulnerability checks |
| `-O` | OS detection | Medium | Operating system fingerprinting |
| `-A` | Aggressive | High | Full enumeration (last resort) |

### Timing Templates

| Flag | Name | Speed | Detection Risk |
|------|------|-------|----------------|
| `-T0` | Paranoid | Very slow | Minimal |
| `-T1` | Sneaky | Slow | Low |
| `-T2` | Polite | Moderate | Low-Medium |
| `-T3` | Normal | Default | Medium |
| `-T4` | Aggressive | Fast | High |

**Recommendation**: Use `-T2` or `-T3` for recon engagements. `-T1` for high-security targets.

### Nmap Output Formats
```bash
# Multiple output formats simultaneously
nmap -sV -p 80,443 <target> -oN scan.txt -oX scan.xml -oG scan.gnmap

# -oN: Normal (human-readable)
# -oX: XML (tool integration, can import to Metasploit)
# -oG: Grepable (quick parsing)
```

## 3. Service-Specific Enumeration

### Web Services (80/443)
```bash
# HTTP methods allowed
nmap --script http-methods -p 80,443 <target>

# Web server info
nmap --script http-server-header -p 80,443 <target>

# Directory/path discovery (careful — high noise)
nmap --script http-enum -p 80,443 <target>

# TLS/SSL analysis
nmap --script ssl-enum-ciphers -p 443 <target>
nmap --script ssl-cert -p 443 <target>

# WAF detection
nmap --script http-waf-detect -p 80,443 <target>
```

### SSH (22)
```bash
nmap --script ssh2-enum-algos -p 22 <target>
nmap --script ssh-hostkey -p 22 <target>
nmap --script ssh-auth-methods -p 22 <target>
```

### DNS (53)
```bash
nmap --script dns-nsid -p 53 <target>
nmap --script dns-recursion -p 53 <target>
```

### SMTP (25/587)
```bash
nmap --script smtp-commands -p 25,587 <target>
nmap --script smtp-enum-users --script-args smtp-enum-users.methods=VRFY -p 25 <target>
```

### SMB (445)
```bash
nmap --script smb-enum-shares,smb-enum-users,smb-os-discovery -p 445 <target>
nmap --script smb-vuln* -p 445 <target>
```

### SNMP (161/UDP)
```bash
nmap -sU --script snmp-info,snmp-interfaces,snmp-processes -p 161 <target>
```

## 4. Web Directory & Content Discovery

### ffuf (Fast Web Fuzzer)
```bash
# Directory discovery
ffuf -u https://<target>/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,301,302,403

# File extension fuzzing
ffuf -u https://<target>/FUZZ -w /usr/share/wordlists/dirb/common.txt -e .php,.asp,.aspx,.jsp,.html,.js,.json,.xml,.txt,.bak,.old

# Subdomain fuzzing via Host header
ffuf -u https://<target>/ -H "Host: FUZZ.<target>" -w /usr/share/wordlists/subdomains.txt -fs <default_size>

# API endpoint discovery
ffuf -u https://<target>/api/FUZZ -w /usr/share/wordlists/api-endpoints.txt -mc 200,201,401,403

# Save JSON output
ffuf -u https://<target>/FUZZ -w wordlist.txt -o ffuf_results.json -of json
```

### gobuster (Alternative)
```bash
gobuster dir -u https://<target> -w /usr/share/wordlists/dirb/common.txt -o gobuster_<target>.txt
gobuster dns -d <target> -w /usr/share/wordlists/subdomains.txt
```

## 5. Vulnerability Scanning

### nuclei (Template-Based Scanner)
```bash
# Critical and high severity only (recommended start)
nuclei -u https://<target> -severity critical,high -o nuclei_<target>.txt

# Specific template categories
nuclei -u https://<target> -tags cve,misconfig,exposure
nuclei -u https://<target> -tags takeover

# Scan list of URLs from httpx
nuclei -l httpx_live.txt -severity critical,high,medium

# Rate limiting for stealth
nuclei -u https://<target> -rl 10 -severity critical,high

# JSON output
nuclei -u https://<target> -severity critical,high -json -o nuclei.json
```

### nikto (Web Server Scanner)
```bash
# Basic scan
nikto -h https://<target> -o nikto_<target>.txt

# Specific tuning options
nikto -h https://<target> -Tuning 1234 -o nikto_<target>.txt
# 1=Interesting files, 2=Misconfigs, 3=Info disclosure, 4=Injection (XSS/SQL)
```

## 6. SSL/TLS Analysis

### testssl.sh
```bash
# Comprehensive TLS test
testssl.sh https://<target>

# Quick check — vulnerable protocols only
testssl.sh --vulnerable https://<target>

# Check specific vulnerabilities
testssl.sh --heartbleed --ccs --robot --breach https://<target>
```

### Key TLS Findings
- **SSLv3 / TLS 1.0 / TLS 1.1**: Deprecated protocols → compliance issue
- **Weak ciphers**: RC4, DES, 3DES, NULL → cryptographic weakness
- **Missing HSTS**: No HTTP Strict Transport Security → downgrade risk
- **Certificate issues**: Expired, self-signed, wrong CN/SAN → trust issues

## 7. Banner Grabbing

### Netcat
```bash
# TCP banner grab
echo "" | nc -nv -w 3 <target_ip> <port>

# Multiple ports
for port in 22 80 443 8080; do
    echo "--- Port $port ---"
    echo "" | nc -nv -w 3 <target_ip> $port 2>&1
done
```

### curl for HTTP Services
```bash
# Full response headers
curl -sI -L https://<target>

# Follow redirects and show chain
curl -sIL https://<target> 2>&1 | grep -E "^(HTTP/|Location:)"
```

## 8. Authentication & Directory Service Enumeration

### LDAP (389/636)
```bash
# Anonymous LDAP bind test
nmap --script ldap-rootdse -p 389 <target>
nmap --script ldap-search --script-args 'ldap.qfilter=users' -p 389 <target>

# ldapsearch if available
ldapsearch -x -H ldap://<target> -b "dc=example,dc=com" -s base namingContexts
```

### Kerberos (88)
```bash
# Kerberos service detection
nmap --script krb5-enum-users --script-args krb5-enum-users.realm='DOMAIN.COM' -p 88 <target>
```

### RDP (3389)
```bash
nmap --script rdp-enum-encryption,rdp-ntlm-info -p 3389 <target>
```

### FTP (21)
```bash
nmap --script ftp-anon,ftp-syst -p 21 <target>
# Check for anonymous access
```

### Redis (6379) / MongoDB (27017) / Elasticsearch (9200)
```bash
# Unauthenticated access checks
nmap -sV -p 6379 <target> --script redis-info
nmap -sV -p 27017 <target> --script mongodb-info
curl -s http://<target>:9200/ | python3 -m json.tool
curl -s http://<target>:9200/_cat/indices
```

## 9. IPv6 Scanning

```bash
# Check for AAAA records
dig <target> AAAA +short

# IPv6 port scan (if AAAA records found)
nmap -6 -sS -sV --top-ports 100 <ipv6_address>

# IPv6 neighbor discovery (local network)
nmap -6 --script targets-ipv6-multicast-echo <interface>
```

**Why IPv6 matters:** Many organizations deploy IPv6 without the same firewall
rules as IPv4. Services may be exposed on IPv6 that are filtered on IPv4.

## 10. Parallel Execution Strategy

### Scan Orchestration
```bash
# Run independent scans in parallel (use & and wait)
nmap -sS -sV --top-ports 1000 <target1> -oN nmap_t1.txt &
nmap -sS -sV --top-ports 1000 <target2> -oN nmap_t2.txt &
wait

# Parallel web fuzzing across multiple hosts
cat live_hosts.txt | while read host; do
  ffuf -u "$host/FUZZ" -w /usr/share/wordlists/dirb/common.txt \
    -mc 200,301,302,403 -o "ffuf_$(echo $host | tr '/:' '_').json" -of json &
  # Limit concurrent jobs
  [ $(jobs -r | wc -l) -ge 3 ] && wait -n
done
wait
```

### Rate Distribution
When scanning multiple targets, distribute rate limits:
- 3 parallel scans at 30 req/sec each = 90 req/sec total from your IP
- Adjust per-scan rate to stay within aggregate OPSEC threshold

## 11. Network Topology Mapping

### Traceroute
```bash
# ICMP traceroute
traceroute <target>

# TCP traceroute (more firewall-friendly)
nmap --traceroute -p 443 <target>
```

### Network Sweep (Use Sparingly)
```bash
# Ping sweep — only within authorized scope
nmap -sn <target_network>/24

# ARP sweep (local network only)
nmap -PR -sn <target_network>/24
```

## 12. Workflow: Active Recon Sequence

1. **Target Selection** → From passive recon, pick high-value IPs/domains
2. **Port Discovery** → SYN scan on top ports (`-sS --top-ports 1000`)
3. **IPv6 Check** → Scan AAAA records if found
4. **Service Identification** → Version detection on open ports (`-sV`)
5. **Script Enumeration** → Targeted NSE scripts for identified services
6. **Auth Service Enumeration** → LDAP, Kerberos, RDP, FTP, databases
7. **Web Content Discovery** → ffuf/gobuster on web services (→ hand off to `web-recon` for deep enumeration)
8. **Vulnerability Scanning** → nuclei on live web targets
9. **SSL/TLS Analysis** → testssl.sh on HTTPS services
10. **Banner Grabbing** → Manual verification of interesting services
11. **Synthesis** → Merge with passive findings, produce final attack surface map

## 13. Error Handling

| Problem | Cause | Solution |
|---------|-------|----------|
| nmap "host seems down" | ICMP filtered | Add `-Pn` (skip host discovery) |
| nmap extremely slow | Too many ports + version detection | Split: port discovery first (`-sS`), then `-sV` on open ports only |
| ffuf 429 responses | Rate limited by WAF | Reduce `-rate` to 5, add `-p 1-3` for random delay |
| nuclei template errors | Outdated templates | Run `nuclei -update-templates` first |
| testssl.sh timeout | Target very slow | Add `--connect-timeout 10 --openssl-timeout 10` |
| Banner grab empty | Service requires protocol-specific handshake | Use service-specific probes (HTTP GET, EHLO, etc.) |

## 14. Common Pitfalls

- **Scanning too broadly**: Only scan IPs confirmed in scope
- **Ignoring UDP**: Critical services (DNS, SNMP, NTP) run on UDP
- **Not saving results**: Always use `-oN` / `-oX` flags — scans are expensive to repeat
- **Aggressive timing on sensitive targets**: Start slow, increase only if needed
- **Forgetting IPv6**: Check for AAAA records and scan IPv6 addresses too
- **Skipping web fuzzing**: Many findings are behind non-obvious paths
- **Running nuclei without rate limiting**: Can trigger WAF blocks and alert the SOC
- **Not checking auth services**: LDAP anonymous bind, Redis no-auth, MongoDB no-auth are common critical findings
- **Sequential when parallel is safe**: Independent targets can be scanned concurrently
