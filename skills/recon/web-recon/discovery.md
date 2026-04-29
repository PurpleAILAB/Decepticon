---
name: web-discovery
description: "Web app discovery — directory/file fuzzing, vhost discovery, JavaScript endpoint extraction."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "directory fuzzing, ffuf, gobuster, vhost discovery, host header, JavaScript analysis, source map, JS endpoint extraction"
  tags: ffuf, gobuster, vhost, javascript-analysis, source-maps
  mitre_attack: T1595.003
---

# Web Discovery — Directories, vHosts, JavaScript

Surface the application's path tree, alternate virtual hosts, and JS-embedded endpoints/secrets. This is the first pass of web recon — feeds every later sub-skill.

## 1. Directory & File Discovery

### ffuf (Recommended — Fast, Flexible)
```bash
# Basic directory fuzzing
ffuf -u https://<target>/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,301,302,403

# With file extensions
ffuf -u https://<target>/FUZZ -w /usr/share/wordlists/dirb/common.txt \
    -e .php,.asp,.aspx,.jsp,.html,.js,.json,.xml,.txt,.bak,.old,.sql,.zip,.tar.gz

# Filter by response size (exclude default pages)
ffuf -u https://<target>/FUZZ -w wordlist.txt -fs <default_size>

# Recursive scanning (depth 2)
ffuf -u https://<target>/FUZZ -w wordlist.txt -recursion -recursion-depth 2

# Throttled for stealth
ffuf -u https://<target>/FUZZ -w wordlist.txt -rate 10 -mc 200,301,302,403
```

### Sensitive Files to Check
```bash
# Common sensitive paths
for path in .env .git/config .htaccess robots.txt sitemap.xml \
    wp-config.php web.config server-status .DS_Store \
    backup.sql dump.sql database.sql .svn/entries \
    crossdomain.xml clientaccesspolicy.xml; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://<target>/$path")
    echo "$code $path"
done
```

## 2. Virtual Host (vHost) Discovery

```bash
# vHost fuzzing via Host header
ffuf -u https://<target_ip>/ -H "Host: FUZZ.<target>" \
    -w /usr/share/wordlists/subdomains.txt -fs <default_size>

# With TLS SNI
ffuf -u https://FUZZ.<target>/ -w /usr/share/wordlists/subdomains.txt \
    -mc 200,301,302,403 -fs <default_size>
```

**Why vHost discovery matters:**
- Multiple applications may share one IP but respond differently based on Host header
- Internal/staging apps often hidden behind non-public vhost names

## 3. JavaScript Analysis

### Endpoint Extraction from JS
```bash
# Download all JS files
curl -s https://<target> | grep -oP 'src="[^"]*\.js"' | cut -d'"' -f2 | while read js; do
    [[ "$js" == http* ]] || js="https://<target>$js"
    echo "=== $js ==="
    curl -s "$js" | grep -oP '["'"'"'](/[a-zA-Z0-9_/\-\.]+)["'"'"']' | sort -u
done

# Look for API keys, secrets, endpoints in JS
curl -s "https://<target>/main.js" | grep -oiE '(api[_-]?key|secret|token|password|auth)["\s]*[:=]["\s]*[a-zA-Z0-9+/=_\-]{8,}'
```

### Source Map Detection
```bash
# Check for exposed source maps
curl -sI "https://<target>/main.js" | grep -i sourcemap
curl -s "https://<target>/main.js.map" | head -c 100
```
