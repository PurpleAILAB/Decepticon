---
name: opsec
description: "Operational security management — traffic shaping, scan rate limiting, source IP management, tool signature avoidance, evidence handling, anti-detection patterns."
allowed-tools: Bash Read
metadata:
  subdomain: opsec
  when_to_use: "OPSEC check, rate limit, stealth, detection avoidance, scan timing, user-agent, scope check, evidence handling, clean up, anti-detection"
  tags: opsec, stealth, rate-limit, user-agent, scope-check, evidence-handling, anti-detection
  mitre_attack: T1562, T1070, T1036
---

# Operational Security (OPSEC) Knowledge Base

OPSEC ensures the red team engagement remains covert, controlled, and within authorized scope. Poor OPSEC burns the engagement — detected scans alert the blue team, taint findings, and waste client resources. This skill applies across all recon phases.

## 1. Core OPSEC Principles

### The OPSEC Mindset
1. **Every packet is a signal** — assume the target has IDS/IPS, SIEM, and SOC analysts
2. **Minimize footprint** — collect only what you need, no more
3. **Blend with normal traffic** — timing, volume, and patterns should look legitimate
4. **Know your tools' signatures** — every scanner has a fingerprint
5. **Document everything** — if you can't prove it was authorized, it wasn't

### Engagement Scope Awareness
Before ANY active operation:
- [ ] Written Rules of Engagement (ROE) on file
- [ ] Target IP ranges and domains explicitly listed
- [ ] Out-of-scope assets clearly identified
- [ ] Testing window defined (dates, times)
- [ ] Emergency contact for the client (for accidental impact)
- [ ] Get-out-of-jail letter accessible

## 2. Network OPSEC

### Scan Rate Limiting

| Target Type | Recommended Rate | Timing Flag |
|-------------|-----------------|-------------|
| Production web server | 5-10 req/sec | nmap `-T2` |
| Internal network | 50-100 req/sec | nmap `-T3` |
| Development/staging | 100+ req/sec | nmap `-T4` |
| High-security target | 1-2 req/sec | nmap `-T1` |
| WAF-protected | 1-5 req/sec | Custom delays |

### Traffic Shaping
```bash
# nmap with specific rate limiting
nmap -sS --max-rate 10 --max-retries 1 -p 80,443 <target>

# ffuf with rate limiting
ffuf -u https://<target>/FUZZ -w wordlist.txt -rate 5

# nuclei with rate limiting
nuclei -u https://<target> -rl 5 -c 2

# curl with delay between requests
for url in $(cat urls.txt); do
    curl -s -o /dev/null -w "%{http_code} $url\n" "$url"
    sleep 2
done
```

### Timing Considerations
- **Business hours (9am-5pm target timezone)**: Higher baseline traffic → scanning blends in
- **Weekends/holidays**: Lower baseline → scans stand out more
- **Maintenance windows**: If known, ideal for aggressive scanning
- **Burst vs sustained**: Short bursts with long pauses are less detectable than sustained scanning

## 3. HTTP OPSEC

### User-Agent Management

> **Important**: User-Agent strings become stale quickly. Always use **current** browser version strings that match real-world traffic at the time of engagement. Check your own browser's UA or query a live UA database before starting.

```bash
# Step 1: Get a current, real User-Agent from your own browser or a live source
# Option A: Copy from your browser's DevTools (Network tab → Request Headers)
# Option B: Use a curated list — update version numbers to match current releases

# Step 2: Build a rotation list with CURRENT versions
# Template — replace <CHROME_VER> and <FIREFOX_VER> with latest stable versions
UA_LIST=(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/<CHROME_VER> Safari/537.36"
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/<CHROME_VER> Safari/537.36"
    "Mozilla/5.0 (X11; Linux x86_64; rv:<FIREFOX_VER>) Gecko/20100101 Firefox/<FIREFOX_VER>"
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:<FIREFOX_VER>) Gecko/20100101 Firefox/<FIREFOX_VER>"
)
UA="${UA_LIST[$RANDOM % ${#UA_LIST[@]}]}"

curl -s -A "$UA" https://<target>/

# ffuf with custom user agent
ffuf -u https://<target>/FUZZ -w wordlist.txt -H "User-Agent: $UA"
```

### Header Hygiene
```bash
# Avoid tool-specific headers that reveal scanner identity
# BAD: Default tool user agents
# - "Nmap Scripting Engine"
# - "nikto"
# - "gobuster"
# - "sqlmap"

# GOOD: Mimic real browser headers (use current browser versions!)
curl -s https://<target>/ \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/<CURRENT_VER> Safari/537.36" \
    -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8" \
    -H "Accept-Language: en-US,en;q=0.9" \
    -H "Accept-Encoding: gzip, deflate, br"
```

## 4. Tool Signature Awareness

### Common IDS/WAF Signatures

| Tool | Detection Signature | Mitigation |
|------|-------------------|------------|
| nmap | SYN scan pattern, probe ordering | Use `-T2`, `--data-length` |
| nikto | Default User-Agent, predictable paths | Custom UA, selective tuning |
| sqlmap | Parameter tampering patterns | Not applicable to recon phase |
| ffuf | Rapid sequential requests | Rate limiting (`-rate`) |
| nuclei | Template-specific payloads | Rate limiting (`-rl`), selective templates |
| gobuster | Sequential path enumeration | Randomize wordlist, rate limit |

### Reducing Scanner Fingerprint
```bash
# nmap — add random data to packets
nmap -sS --data-length 24 -T2 <target>

# nmap — randomize host order (for multi-target)
nmap -sS --randomize-hosts -iL targets.txt

# nmap — spoof source port (use common ports)
nmap -sS -g 53 <target>  # Appear as DNS traffic
nmap -sS -g 80 <target>  # Appear as HTTP traffic
```

## 5. Source Management

### IP Awareness
- **Know your egress IP**: `curl -s ifconfig.me`
- **Single source**: All scans originate from the sandbox — the target will see one IP
- **VPN/proxy considerations**: If engagement allows, rotate exit nodes
- **Cloud instances**: Ephemeral cloud VMs provide disposable IPs

### DNS OPSEC
```bash
# Use public resolvers to avoid leaking internal DNS queries
dig @8.8.8.8 <target> A +short
dig @1.1.1.1 <target> A +short

# Don't use target's own DNS servers for recon queries
# (they may log all queries from unknown sources)
```

## 6. Evidence & Data Handling

### Engagement Documentation
Every action should be logged:
```markdown
| Timestamp (UTC) | Action | Target | Tool | Justification |
|-----------------|--------|--------|------|---------------|
| <YYYY-MM-DD HH:MM> | SYN scan top 1000 | 10.0.1.50 | nmap | Passive recon identified as primary web server |
| <YYYY-MM-DD HH:MM> | Dir fuzzing | api.example.com | ffuf | Port 443 open, REST API suspected |
```

### Data Classification
- **Workspace files**: All scan output goes to the engagement directory — treat as engagement artifacts
- **Credentials found**: NEVER store in plaintext — immediately document and encrypt
- **PII discovered**: Note existence, do not exfiltrate — document for client
- **Client data**: Handle per engagement contract data handling requirements

### Clean-Up Protocol
After engagement:
- [ ] All tools stopped
- [ ] No persistent connections to target
- [ ] Scan data secured per client requirements
- [ ] Temporary files cleaned from sandbox
- [ ] No data left on third-party services (Shodan searches, etc.)

## 7. Scope Enforcement

### Automated Scope Checking
```bash
# Before scanning, verify target is in scope
SCOPE_FILE="scope.txt"
TARGET="10.0.1.50"

if grep -q "$TARGET" "$SCOPE_FILE" 2>/dev/null; then
    echo "IN SCOPE — proceed"
else
    echo "WARNING: $TARGET not found in scope file!"
    echo "Verify before proceeding."
fi
```

### Scope Boundaries
- **IP ranges**: Only scan IPs explicitly listed in scope document
- **Domains**: Only enumerate subdomains of authorized root domains
- **Cloud resources**: Only test resources confirmed as client-owned
- **Third-party services**: DO NOT test shared infrastructure (CDNs, SaaS platforms)
- **Physical scope**: Only applicable if physical penetration test is authorized

### Accidental Out-of-Scope
If you accidentally touch an out-of-scope system:
1. **Stop immediately**
2. **Document the incident** (timestamp, target, action taken)
3. **Notify the engagement lead**
4. **Do NOT attempt to "clean up" evidence** — this makes it worse

## 8. Detection Indicators to Monitor

### Signs You've Been Detected
- **Connection resets**: Target suddenly dropping connections → firewall rule added
- **Rate limiting**: 429 responses where 200s were before → WAF triggered
- **IP block**: Timeouts on previously responsive hosts → IP banned
- **Honeypot indicators**: Unusually easy targets, too-good-to-be-true services
- **Tarpit responses**: Extremely slow responses → deliberately slowing scanner

### Response to Detection
1. **Pause all scanning** — at least 30 minutes
2. **Assess what triggered detection** — review recent scan patterns
3. **Reduce scan rate** by 50-75%
4. **Consider different approach** — passive only for a period
5. **Document the detection event** for engagement report

## 9. OPSEC Checklist (Pre-Engagement)

- [ ] ROE document reviewed and understood
- [ ] Scope file created at `scope.txt`
- [ ] Emergency client contact accessible
- [ ] Egress IP noted: `curl -s ifconfig.me`
- [ ] Tool user agents configured (non-default)
- [ ] Scan rate limits configured per target type
- [ ] Output directory structure created
- [ ] Evidence logging template ready
- [ ] Clean-up protocol documented
