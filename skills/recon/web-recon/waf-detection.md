---
name: web-waf-detection
description: "Web Application Firewall fingerprinting — Cloudflare, AWS WAF, Akamai, Imperva, etc."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "WAF detection, wafw00f, Cloudflare, AWS WAF, Akamai, Imperva, web shield"
  tags: waf-detection
  mitre_attack: T1592.004
---

# WAF Detection & Fingerprinting

Identify any front-end shield (Cloudflare, AWS WAF, Akamai, Imperva, etc.) so exploit can choose appropriate evasion (encoding, payload obfuscation, alternate transport). A multi-proxy/CDN stack is also the recognition signal for HTTP request smuggling — note this for handoff.

## Tooling

```bash
# wafw00f
wafw00f https://<target>

# Manual detection via response patterns
curl -s "https://<target>/?id=1' OR '1'='1" -I | grep -iE '(server|x-cdn|cf-ray|x-sucuri|x-aws)'
```

## Known WAF Indicators

| WAF | Signal |
|-----|--------|
| Cloudflare | `CF-RAY` header, `__cfduid` cookie |
| AWS WAF | `x-amzn-requestid` header |
| Akamai | `AkamaiGHost` server header |
| Imperva | `X-CDN` header, `incap_ses` cookie |
| Sucuri | `X-Sucuri-ID` header |
| F5 BIG-IP | `BIGipServer` cookie |

## Multi-Proxy / Smuggling Signal

If the response chain shows TWO different `Server:` strings on subsequent requests, or a CDN front in front of an origin server with different framing, **note this in the handoff under "Frontend stack"** — it is the recognition signal for HTTP request smuggling routing in exploit.
