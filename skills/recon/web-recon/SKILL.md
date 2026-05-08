---
name: web-recon
description: "Web application enumeration hub — directory/file fuzzing, vhost discovery, API enumeration, CMS scanning, WAF detection, auth surface mapping, cookie audit."
allowed-tools: Read
metadata:
  subdomain: reconnaissance
  when_to_use: "web recon, web application enumeration, web app fingerprint"
  tags: web-recon
  mitre_attack: T1595.003, T1592.004
---

# Web Application Reconnaissance — Hub

Sub-skills under this directory:

| Sub-skill | Path | When to load |
|---|---|---|
| Discovery | `load_skill("/skills/recon/web-recon/discovery.md")` | directory/file fuzzing, vhost, JS analysis |
| API enumeration | `load_skill("/skills/recon/web-recon/api-enumeration.md")` | REST/GraphQL/parameter fuzzing |
| CMS scanning | `load_skill("/skills/recon/web-recon/cms-scanning.md")` | WordPress/Joomla/Drupal detected |
| WAF detection | `load_skill("/skills/recon/web-recon/waf-detection.md")` | proxy/CDN suspected |
| Auth mapping | `load_skill("/skills/recon/web-recon/auth-mapping.md")` | login flow analysis |
| Cookie audit | `load_skill("/skills/recon/web-recon/cookie-audit.md")` | sink behind session, race-condition recon |

For overall recon workflow, scope rules, and handoff format, see `load_skill("/skills/recon/workflow.md")` (root workflow).

## Tag-Driven Fast Paths

When the orchestrator passes challenge tags, skip straight to the matching sub-skill:

| Tag | First action | Sub-skill to load |
|-----|-------------|-------------------|
| `sqli` | Fire a single error-triggering payload on every form/param | `/skills/exploit/web/sqli.md` recon section |
| `ssti` | Probe every reflection point with `{{7*7}}` | `/skills/exploit/web/ssti.md` recon section |
| `lfi` | Path-traversal probe on every file/path param | discovery.md |
| `idor` | Enumerate object IDs on every user-data endpoint | api-enumeration.md |
| `auth` | Map the full auth flow before other recon | auth-mapping.md |

## HTTP Request Deduplication Pattern

When iterating parameters (IDs, pages, paths), always deduplicate via `recon/probed.txt` to avoid re-probing the same URLs after context summarization:

```bash
URL="http://<TARGET>/api/resource/$ID"
if grep -Fxq "$URL" recon/probed.txt 2>/dev/null; then
  echo "SKIP: $URL"
else
  echo "$URL" >> recon/probed.txt
  curl -sS "$URL" -o /tmp/probe.html -w '%{http_code}\n'
  head -10 /tmp/probe.html
fi
```

**Resume rule**: Before any scan loop, check `tail -1 recon/probed.txt` to find the last probed item and continue from there — not from the beginning.

**Stop rule**: If 5 consecutive probes return the same status code + same response size (±50 bytes), stop that enumeration axis and pivot to a different surface.

## Output files

```
./
├── ffuf_<target>_dirs.json         # Directory fuzzing results
├── ffuf_<target>_vhosts.json       # Virtual host discovery
├── ffuf_<target>_api.json          # API endpoint fuzzing
├── web_sensitive_<target>.txt      # Sensitive file check results
├── js_endpoints_<target>.txt       # Extracted JS endpoints
├── wpscan_<target>.json            # WordPress scan (if applicable)
└── web_recon_<target>_summary.md   # Consolidated web findings
```
