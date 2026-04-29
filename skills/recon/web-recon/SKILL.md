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
| Discovery | `read_file("/skills/recon/web-recon/discovery.md")` | directory/file fuzzing, vhost, JS analysis |
| API enumeration | `read_file("/skills/recon/web-recon/api-enumeration.md")` | REST/GraphQL/parameter fuzzing |
| CMS scanning | `read_file("/skills/recon/web-recon/cms-scanning.md")` | WordPress/Joomla/Drupal detected |
| WAF detection | `read_file("/skills/recon/web-recon/waf-detection.md")` | proxy/CDN suspected |
| Auth mapping | `read_file("/skills/recon/web-recon/auth-mapping.md")` | login flow analysis |
| Cookie audit | `read_file("/skills/recon/web-recon/cookie-audit.md")` | sink behind session, race-condition recon |

For overall recon workflow, scope rules, and handoff format, see `read_file("/skills/recon/workflow.md")` (root workflow).

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
