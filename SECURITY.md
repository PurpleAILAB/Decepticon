# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in Decepticon, please report it responsibly:

1. **GitHub Security Advisories** (preferred): Use [GitHub's private vulnerability reporting](https://github.com/PurpleAILAB/Decepticon/security/advisories/new) to submit a report directly. If this link returns a 404, the feature may be pending enablement — use the email method below instead.

2. **Email**: Contact the maintainers at **purpleailab@gmail.com** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)

## What to Report

- Vulnerabilities in Decepticon's code (agent logic, sandbox escapes, credential handling)
- Docker container security issues (privilege escalation, network isolation bypass)
- Dependency vulnerabilities that directly affect Decepticon
- Insecure default configurations

## What NOT to Report

- Vulnerabilities in target systems that Decepticon is designed to test (that's the point)
- General security best practices or hardening suggestions (open a regular issue instead)
- Vulnerabilities in third-party services not bundled with Decepticon

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 7 days
- **Fix or mitigation**: Dependent on severity, typically within 30 days

## Responsible Use

Decepticon is an offensive security tool designed for **authorized** red team engagements only. Users are responsible for ensuring they have proper authorization before using Decepticon against any target. See the [LICENSE](LICENSE) for terms of use.

## Web dashboard authentication

The web dashboard (default `http://localhost:3000`) and the terminal WebSocket (default `ws://localhost:3003`) are **unauthenticated by design** in the upstream stack. The threat model assumes a single operator on a single host: both ports bind to `localhost`, and anyone with shell access to that host can already drive the agent.

That model breaks the moment the ports are reachable from another machine — VPN, tailscale subnet routing, port-forward through a reverse proxy, accidentally binding `0.0.0.0` in compose, etc. At that point an unauthenticated remote caller can execute arbitrary commands in the sandbox, exfiltrate engagement data, and modify findings.

The `DECEPTICON_WEB_AUTH` env var (introduced in the `decepticon-mac` fork) is an **opt-in** hardening switch. The default is unchanged — operators who don't set it see the same behavior as upstream.

### Modes

| Value | Effect |
|---|---|
| `none` (default, unset, or empty) | No authentication. Today's upstream behavior. Safe only on localhost. |
| `password:<scrypt-hash>` | HTTP basic auth on every API route; the terminal WS handshake requires a token derived from the same hash. |
| `disable-bind-public` | The terminal server refuses to bind to anything other than 127.0.0.1 / ::1 / localhost. Defense in depth for deployments that should never be remote. |

Malformed values throw at startup — Decepticon will not silently downgrade to "no auth" if you fat-finger the env var.

### Generating a password hash

The hash format is `scrypt$N$r$p$<base64-salt>$<base64-key>`. The scrypt parameters default to `N=16384, r=8, p=1` (the Node `crypto` defaults), which OWASP rates as adequate for an interactive login flow on modern hardware. Operators on slower hardware can raise `N` to 32768 or 65536.

From inside `clients/web/`, you can produce a hash with a one-liner. Example (from the repo root):

```bash
cd clients/web
npx tsx -e 'import("./src/lib/auth-mode.ts").then(m => console.log(m.hashPassword(process.argv[1])))' 'your-strong-password'
```

Set the result as the env var:

```bash
DECEPTICON_WEB_AUTH=password:scrypt$16384$8$1$<salt>$<key>
```

The hash itself is sensitive — anyone who can read it can mint valid terminal-WS tokens (it's the HMAC key for the WS handshake). Treat it like a password: keep `~/.decepticon/.env` mode 0600 and never commit it.

### Why scrypt rather than bcrypt

The fork uses Node's built-in `crypto.scrypt` rather than bringing in the `bcrypt` npm package:

- No new native-dep build at install time (`bcrypt` ships a node-gyp binding).
- scrypt is a well-respected, memory-hard KDF (RFC 7914) and is the algorithm OWASP recommends alongside argon2 / bcrypt.
- The implementation is in-tree (`clients/web/src/lib/auth-mode.ts`) and auditable — no transitive dep to track CVEs against.

If you'd prefer bcrypt or argon2, replace the `hashPassword` / `verifyPassword` helpers; the rest of the auth bridge doesn't care which KDF was used as long as the env format is `password:<opaque-hash>`.

### Reverse-proxy deployments

If you put Decepticon behind a reverse proxy (nginx, traefik, Caddy), make sure the proxy **forwards** the `Authorization` header rather than terminating basic auth at the proxy and stripping it. Some default proxy configs strip `Authorization` to avoid leaking creds to the upstream — that turns Decepticon's auth into an "always 401" wall. Either:

- Configure the proxy to forward `Authorization` and let Decepticon do the check, or
- Terminate auth at the proxy and bind Decepticon to `127.0.0.1` only (use `DECEPTICON_WEB_AUTH=disable-bind-public` to enforce this), or
- Use both (defense in depth — the proxy is the public auth gate; Decepticon's own auth is a backstop in case the proxy is misconfigured).

### Threat model summary

| Threat | Mitigation |
|---|---|
| Unauthenticated remote driver | `password:` mode requires HTTP basic auth + WS token. |
| Token replay across services | The WS token is HMAC'd over a fixed `decepticon.web-auth.ws-token.v1` label for domain separation. |
| Timing-side-channel on credential compare | `crypto.timingSafeEqual` on both password verification and WS-token compare. |
| Brute force of the scrypt | `N=16384` is OWASP-adequate; raise for sensitive deployments. scrypt is memory-hard, so GPU brute-force is expensive. |
| Accidental public bind | `disable-bind-public` mode hard-fails startup if the configured host isn't loopback. |
| WebSocket bypass of HTTP middleware | The WS handshake is independently authenticated via the token mechanism; the HTTP auth check on web routes is enforced separately in `auth-bridge.ts`. |
| Reverse-proxy strips `Authorization` | Documented above; recommended workaround is loopback bind + proxy-side auth. |

Issues with the auth design should be reported via the same channels as any other security issue (see "Reporting a Vulnerability" above).
