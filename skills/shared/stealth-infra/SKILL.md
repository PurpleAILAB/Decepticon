---
name: stealth-infra
description: "Anti-bot evasion, proxy rotation, credential retrieval from password managers, and stealth HTTP tooling for covert web operations."
allowed-tools: Bash Read
metadata:
  subdomain: opsec
  when_to_use: "stealth, anti-bot, captcha, Cloudflare bypass, WAF evasion, proxy rotation, cookie injection, password manager, keyring, 1Password, GNOME Keyring, OPSEC quiet, anti-detection, TLS fingerprint, browser impersonation"
  tags: stealth, proxy, captcha, anti-bot, opsec, cookies, keyring
  mitre_attack: T1562, T1036, T1090
---

# Stealth Infrastructure — Anti-Bot Evasion & Covert Operations

This skill covers the stealth tooling installed in the sandbox for evading anti-bot systems, rotating proxies, solving CAPTCHAs, and retrieving credentials from password managers. Use these tools when the engagement RoE specifies OPSEC level `quiet` or `silent`, or when targets deploy WAFs/anti-bot shields.

## Available Libraries (Pre-Installed)

| Library | Purpose | When to use |
|---------|---------|-------------|
| **scrapling** | Adaptive scraping with Cloudflare Turnstile bypass, StealthyFetcher | Primary choice for any anti-bot-protected target |
| **curl_cffi** | libcurl with impersonated TLS fingerprints (Chrome/Firefox/Safari) | When you need raw HTTP with real browser TLS |
| **tls_client** | Go-based TLS fingerprint impersonation via Python | Alternative to curl_cffi for different fingerprint profiles |
| **cloudscraper** | Cloudflare v1/v2 challenge solver | Legacy Cloudflare JS challenges |
| **fake-useragent** | Realistic, rotating User-Agent strings | Any HTTP request needing normal-looking UA |
| **proxychains4** | Force any CLI tool through a SOCKS/HTTP proxy chain | Route nmap/curl/subfinder through Tor or proxy |
| **tor** | Onion routing for IP anonymization | When source IP must not be linkable to operator |
| **keyring** | OS keyring access (GNOME Keyring, macOS Keychain, Windows Credential Vault) | Retrieve stored credentials without hardcoding |
| **python-socks** | SOCKS4/5 proxy support for asyncio | Async HTTP through proxies |
| **aiohttp-socks** | aiohttp + SOCKS proxy integration | Async scraping through proxy chains |

## 1. Scrapling — Primary Anti-Bot Bypass

Scrapling's `StealthyFetcher` uses a real Chromium instance with anti-fingerprinting patches. It bypasses Cloudflare Turnstile, Akamai, DataDome, and most JS challenges.

```python
# Stealthy fetch — bypasses Cloudflare Turnstile and most anti-bot
timeout 60 python3 -u -c '
from scrapling.fetchers import StealthyFetcher

page = StealthyFetcher.fetch(
    "https://<TARGET>",
    headless=True,
    network_idle=True,
    disable_resources=True,  # skip images/fonts for speed
)
print(f"Status: {page.status}")
print(f"Title: {page.css(\"title::text\").get()}")
# Extract data
for link in page.css("a[href]"):
    print(f"  {link.attrib[\"href\"]}")
' 2>&1 | tee scrapling_result.txt
```

### With proxy rotation:
```python
timeout 60 python3 -u -c '
from scrapling.fetchers import StealthyFetcher

page = StealthyFetcher.fetch(
    "https://<TARGET>",
    headless=True,
    network_idle=True,
    proxy={"server": "socks5://127.0.0.1:9050"},  # Tor
)
print(page.status, page.css("title::text").get())
'
```

### Session persistence (cookies survive across requests):
```python
timeout 60 python3 -u -c '
from scrapling.fetchers import StealthyFetcher

# First request — login
fetcher = StealthyFetcher()
page = fetcher.fetch("https://<TARGET>/login", headless=True)
# Fill and submit login form...

# Second request — authenticated, same session
page2 = fetcher.fetch("https://<TARGET>/dashboard", headless=True)
print(page2.css("h1::text").get())
'
```

## 2. curl_cffi — TLS Fingerprint Impersonation

Real browser TLS fingerprints without running a browser. Fastest option for API probing.

```python
timeout 30 python3 -u -c '
from curl_cffi import requests

# Impersonate Chrome 131
r = requests.get(
    "https://<TARGET>",
    impersonate="chrome131",
    timeout=10,
)
print(f"Status: {r.status_code}")
print(f"Server: {r.headers.get(\"server\", \"?\")} | CF-RAY: {r.headers.get(\"cf-ray\", \"none\")}")
print(r.text[:500])
'
```

### With proxy:
```python
r = requests.get(
    "https://<TARGET>",
    impersonate="chrome131",
    proxies={"https": "socks5://127.0.0.1:9050"},
    timeout=10,
)
```

### Available impersonation profiles:
- `chrome99` through `chrome131`
- `firefox109`, `firefox133`
- `safari15_3`, `safari18_0`
- `edge99`, `edge101`

## 3. Proxy Infrastructure

### Proxychains (route any CLI tool through proxy)

```bash
# Start Tor (if not running)
tor &
sleep 5

# Route curl through Tor
proxychains4 curl -s https://check.torproject.org/api/ip

# Route any scanner through Tor
proxychains4 subfinder -d <TARGET> -silent
proxychains4 httpx-pd -l subdomains.txt -silent
```

### Free proxy rotation (Proxifly)

```bash
# Download fresh proxy list
curl -sL https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.json -o proxies.json

# Use in Python
timeout 30 python3 -u -c '
import json, random
from curl_cffi import requests

with open("proxies.json") as f:
    proxies = json.load(f)

# Pick a random proxy
proxy = random.choice(proxies)
proxy_url = f"{proxy[\"protocol\"]}://{proxy[\"ip\"]}:{proxy[\"port\"]}"
print(f"Using proxy: {proxy_url} ({proxy.get(\"country\", \"?\")})")

r = requests.get(
    "https://<TARGET>",
    impersonate="chrome131",
    proxies={"https": proxy_url},
    timeout=10,
)
print(f"Status: {r.status_code}")
'
```

### Custom proxy chain (edit /etc/proxychains4.conf)

```bash
# For OPSEC-quiet: chain through your VPN + Tor
cat > /tmp/chain.conf << 'EOF'
strict_chain
proxy_dns
[ProxyList]
socks5 <YOUR_VPN_SOCKS_IP> <PORT>
socks5 127.0.0.1 9050
EOF
proxychains4 -f /tmp/chain.conf curl -s https://<TARGET>
```

## 4. Credential Retrieval from Password Managers

### Python keyring (generic — works with GNOME Keyring, macOS Keychain, KWallet)

```python
timeout 10 python3 -u -c '
import keyring

# Retrieve stored credential
password = keyring.get_password("telenor-vdp", "test-user")
if password:
    print(f"Retrieved password for test-user: {password[:3]}***")
else:
    print("No credential stored. Use: keyring.set_password(\"telenor-vdp\", \"test-user\", \"<password>\")")
'
```

### Store credentials for the engagement:

```python
timeout 10 python3 -u -c '
import keyring
keyring.set_password("telenor-vdp", "test-user", "<PASSWORD>")
print("Credential stored in keyring")
'
```

### 1Password CLI (if configured):

```bash
# Sign in (requires setup)
eval $(op signin)

# Get a credential
op item get "Telenor VDP" --fields username,password --format=json
```

### Cookie injection from file:

```python
# Load cookies exported from browser (Netscape format or JSON)
timeout 30 python3 -u -c '
import json
from curl_cffi import requests

# Load cookies from JSON file (exported via browser extension)
with open("/workspace/cookies.json") as f:
    cookie_data = json.load(f)

# Build cookie jar
cookies = {}
for c in cookie_data:
    cookies[c["name"]] = c["value"]

r = requests.get(
    "https://<TARGET>/dashboard",
    impersonate="chrome131",
    cookies=cookies,
    timeout=10,
)
print(f"Status: {r.status_code}")
print(r.text[:500])
'
```

## 5. CAPTCHA Handling

### Cloudflare Turnstile — Scrapling handles this automatically:
```python
# StealthyFetcher automatically solves Turnstile challenges
page = StealthyFetcher.fetch("https://<TARGET>", headless=True, network_idle=True)
# If Turnstile was present, page.status will be 200 (solved) or 403 (failed)
```

### For other CAPTCHAs (reCAPTCHA, hCaptcha):
1. **Manual solve**: Use Scrapling's StealthyFetcher to render the page, screenshot, solve manually
2. **Token injection**: If you have a CAPTCHA-solving service API key, inject the token:

```python
timeout 60 python3 -u -c '
from curl_cffi import requests

# After obtaining CAPTCHA token from a solving service:
CAPTCHA_TOKEN = "<solved-token>"

r = requests.post(
    "https://<TARGET>/login",
    impersonate="chrome131",
    data={
        "username": "test",
        "password": "test",
        "g-recaptcha-response": CAPTCHA_TOKEN,
    },
    timeout=10,
)
print(r.status_code, r.headers.get("location", ""))
'
```

## 6. Rate Limiting & Traffic Shaping

```python
# Respectful rate-limited scraping
timeout 120 python3 -u -c '
import time, random
from curl_cffi import requests
from fake_useragent import UserAgent

ua = UserAgent()
TARGET = "https://<TARGET>"
PATHS = ["/api/users", "/api/orders", "/api/settings"]

for path in PATHS:
    # Random delay: 2-5 seconds (mimics human)
    time.sleep(random.uniform(2, 5))

    r = requests.get(
        f"{TARGET}{path}",
        impersonate="chrome131",
        headers={"User-Agent": ua.random},
        timeout=10,
    )
    print(f"{r.status_code} {path}: {len(r.text)} bytes")
'
```

## Anti-Patterns (Do NOT)

- **Never** send requests at machine speed without delays — even 100ms intervals look like a scanner
- **Never** use default `python-requests` User-Agent for stealth operations — it's fingerprinted by every WAF
- **Never** hardcode credentials in scripts — use keyring or env vars
- **Never** skip the WAF detection step — knowing what you face determines the right bypass
- **Never** use raw `requests.get()` against Cloudflare — it will always fail; use curl_cffi or scrapling
- **Never** brute-force CAPTCHAs — solve or bypass them; repeated failures trigger IP bans

## Decision Tree

```
Target has anti-bot? → Yes → Which type?
  ├─ Cloudflare Turnstile → StealthyFetcher (automatic)
  ├─ Cloudflare JS Challenge → cloudscraper or StealthyFetcher
  ├─ Akamai/DataDome → StealthyFetcher with proxy rotation
  ├─ reCAPTCHA/hCaptcha → Manual solve or token injection
  └─ Custom WAF → curl_cffi with browser TLS fingerprint

Target has rate limiting? → Yes
  ├─ Soft (429 after N requests) → Add 2-5s random delays
  └─ Hard (IP ban) → Rotate proxies via proxychains4 or Proxifly

OPSEC level quiet/silent?
  ├─ Use Tor for DNS + requests (proxychains4)
  ├─ Rotate User-Agents (fake-useragent)
  └─ Never reuse the same proxy for >10 requests
```
