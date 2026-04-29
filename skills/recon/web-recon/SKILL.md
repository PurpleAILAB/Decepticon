---
name: web-recon
description: "Web application enumeration — directory/file fuzzing, virtual host discovery, API endpoint enumeration, CMS scanning, WAF detection, JavaScript analysis."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "web recon, directory fuzzing, ffuf, gobuster, API enumeration, vhost discovery, JavaScript analysis, CMS scan, wpscan, WAF detection, parameter fuzzing, GraphQL"
  tags: ffuf, gobuster, api-enum, vhost, cms-scan, waf-detection, javascript-analysis
  mitre_attack: T1595.003, T1592.004
---

# Web Application Reconnaissance Knowledge Base

Web application recon goes beyond port scanning — it maps the application layer: routes, APIs, parameters, technologies, and authentication surfaces. This skill covers web-specific enumeration following OWASP Testing Guide methodology.

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

## 3. API Endpoint Enumeration

### REST API Discovery
```bash
# Common API paths
ffuf -u https://<target>/api/FUZZ -w /usr/share/wordlists/api-endpoints.txt -mc 200,201,401,403,405

# Version enumeration
for v in v1 v2 v3; do
    ffuf -u "https://<target>/api/$v/FUZZ" -w api-wordlist.txt -mc 200,201,401,403
done

# Check for Swagger/OpenAPI docs
for doc in swagger.json openapi.json api-docs docs/api swagger/v1/swagger.json; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://<target>/$doc")
    echo "$code $doc"
done
```

### GraphQL Detection
```bash
# Common GraphQL endpoints
for path in graphql graphiql playground api/graphql; do
    # Introspection query
    curl -s -X POST "https://<target>/$path" \
        -H "Content-Type: application/json" \
        -d '{"query":"{__schema{types{name}}}"}' | head -c 200
    echo " → $path"
done
```

### API Key/Token Patterns
Look for in responses:
- `api_key`, `apiKey`, `access_token`, `bearer`, `jwt`
- Base64-encoded blobs in cookies or headers
- `Authorization` header patterns

## 4. Parameter Discovery

```bash
# GET parameter fuzzing
ffuf -u "https://<target>/page?FUZZ=test" -w /usr/share/wordlists/params.txt -mc 200 -fs <default_size>

# POST parameter fuzzing
ffuf -u "https://<target>/login" -X POST \
    -d "FUZZ=test" -H "Content-Type: application/x-www-form-urlencoded" \
    -w /usr/share/wordlists/params.txt -mc 200 -fs <default_size>

# Header fuzzing
ffuf -u "https://<target>/" -H "FUZZ: test" \
    -w /usr/share/wordlists/headers.txt -mc 200 -fs <default_size>
```

## 5. JavaScript Analysis

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

## 6. CMS-Specific Scanning

### WordPress
```bash
# wpscan (comprehensive)
wpscan --url https://<target> --enumerate vp,vt,u,dbe --api-token <WP_API_TOKEN>

# Quick checks
curl -s "https://<target>/wp-json/wp/v2/users" | python3 -m json.tool
curl -s "https://<target>/xmlrpc.php" -d '<methodCall><methodName>system.listMethods</methodName></methodCall>'
curl -s "https://<target>/?author=1" -I | grep Location
```

### Joomla
```bash
# Version detection
curl -s "https://<target>/administrator/manifests/files/joomla.xml" | grep -oP '<version>\K[^<]+'
```

### Drupal
```bash
curl -s "https://<target>/CHANGELOG.txt" | head -5
```

## 7. WAF Detection & Fingerprinting

```bash
# wafw00f
wafw00f https://<target>

# Manual detection via response patterns
curl -s "https://<target>/?id=1' OR '1'='1" -I | grep -iE '(server|x-cdn|cf-ray|x-sucuri|x-aws)'

# Known WAF indicators
# Cloudflare: CF-RAY header, __cfduid cookie
# AWS WAF: x-amzn-requestid header
# Akamai: AkamaiGHost server header
# Imperva: X-CDN header, incap_ses cookie
```

## 8. Authentication Surface Mapping

### Login Endpoint Discovery
```bash
# Common auth paths
for path in login signin auth authenticate oauth/authorize \
    api/auth api/login admin/login wp-login.php; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://<target>/$path")
    [ "$code" != "404" ] && echo "$code https://<target>/$path"
done
```

### Auth Mechanism Identification
- **Cookie-based**: Check `Set-Cookie` headers after login
- **JWT**: Look for `Authorization: Bearer eyJ...` patterns
- **OAuth 2.0**: Check for `/oauth/authorize`, `/oauth/token` endpoints
- **API Key**: Check if `X-API-Key` or `Authorization: ApiKey` is accepted
- **SAML/SSO**: Check for redirects to IdP (Okta, Azure AD, Auth0)

## 9. Cookie-Conditional Sink Discovery

A "sink" (eval, deserialize, exec, template render) may behave differently — or not fire at all — depending on which session cookies are present. Recon MUST enumerate every cookie the app sets and re-test each candidate sink with and without each cookie before declaring the sink unreachable. Skipping this step is the most common cause of exploit handing back a false "blind sink" verdict.

### Procedure
1. Walk the app unauthenticated; record every `Set-Cookie` (name, attributes, source endpoint).
2. Authenticate (every auth tier: anon, low-priv user, high-priv user) and record the full cookie jar after each.
3. For each candidate sink (parameter, route, header, body field):
   - Probe with NO cookies.
   - Probe with FULL authenticated jar.
   - Bisect: drop one cookie at a time and re-probe. The cookie whose removal silences the sink is the gating cookie.
4. Document a "Sink preconditions" table in `recon_notes.md` and `SUMMARY.txt`:

| Sink | Endpoint | Method | Required cookies | Behavior w/o cookie | Behavior w/ cookie | Notes |
|------|----------|--------|------------------|--------------------|--------------------|-------|
| `bookmark_data` (deser) | `/bookmarks/import` | POST | `session=...; auth_tier=user` | 302 → /login | 200 + processed | gated by auth_tier |

5. In the handoff to exploit/postexploit, ALWAYS include a **Required session state** line:

```
Required session state: cookies=[session, auth_tier=user]; obtained via POST /login (creds: user@example.com / hunter2)
```

If recon hands off without this line, exploit is required to re-run cookie enumeration before concluding any sink is unreachable.

## 10. Workflow: Web Recon Sequence

1. **Technology Fingerprint** → httpx with tech-detect, check headers
2. **Directory Discovery** → ffuf with common wordlist + extensions
3. **Sensitive Files** → Check .env, .git, backups, config files
4. **vHost Discovery** → Host header fuzzing
5. **API Enumeration** → Swagger docs, REST/GraphQL endpoints
6. **JS Analysis** → Extract endpoints, secrets from JavaScript
7. **CMS Scanning** → If WordPress/Joomla/Drupal detected, run specific tools
8. **WAF Detection** → Identify and document WAF presence
9. **Auth Surface** → Map all authentication mechanisms
10. **Parameter Discovery** → Fuzz GET/POST parameters on key endpoints

## 11. Output Files
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
