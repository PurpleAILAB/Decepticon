# Decepticon Telemetry

Decepticon can send **anonymous usage telemetry** to help maintainers see what
users ask the agents to do and what the agents actually do. It is **opt-in** and
designed for a red-team threat model: **raw prompts, targets, credentials, and
tool output are never transmitted.**

## TL;DR

- **Off by default.** Nothing is sent unless you set `DECEPTICON_TELEMETRY=basic`
  (or `extended`) **and** a `DECEPTICON_TELEMETRY_ENDPOINT`.
- **`DO_NOT_TRACK=1`** (or `decepticon-cli telemetry off`) forces it off forever.
- **See exactly what would be sent:** `decepticon-cli telemetry preview`.

## Controls

| Variable / command | Effect |
|---|---|
| `DECEPTICON_TELEMETRY=off\|basic\|extended` | consent mode (default `off`) |
| `DO_NOT_TRACK=1` | standard kill switch — forces `off` |
| `DECEPTICON_TELEMETRY_ENDPOINT=<url>` | gateway URL; unset ⇒ nothing is sent |
| `decepticon-cli telemetry status` | show resolved mode / endpoint / anonymous id |
| `decepticon-cli telemetry preview` | print the exact payload for a sample run |
| `decepticon-cli telemetry off` / `on` | persistent opt-out marker (overrides env) |

## What is collected

Two consent tiers map to the data tiers in the design doc:

- **`basic` → Tier A (structural, always safe):** event type, agent name, tool
  name (e.g. `nmap`), normalized status, bucketed sizes, token counts, model id,
  and any MITRE/CWE/CVE ids the run already produced.
- **`extended` → Tier A + B (sanitized semantic):** additionally a coarse
  request/finding **classification enum** and attack phase. Still no free text.

Every batch carries a non-identifying envelope: a random `install_id` (a UUID
minted on first use — never machine- or IP-derived), the Decepticon version, and
the OS family (`linux`/`darwin`/`windows`).

### Example (exactly what leaves the machine)

```json
{
  "schema_version": "1.0",
  "tier": "A",
  "install_id": "1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
  "client": { "decepticon_version": "1.1.13", "os": "linux" },
  "events": [
    { "type": "tool.call",   "ts": 2.0, "agent": "recon", "tool": "bash" },
    { "type": "tool.result", "ts": 3.0, "agent": "recon", "tool": "bash",
      "status": "ok", "output_bucket": "1k-10k" },
    { "type": "finding.created", "ts": 4.0, "agent": "exploit",
      "tool": "validate_finding", "cwe": ["CWE-89"], "mitre_techniques": ["T1190"] }
  ]
}
```

## What is NEVER collected (Tier C)

Raw prompts, target IPs / domains / hosts, credentials, file contents, tool
output, and client/org names. These are blocked by **three independent layers**:

1. **Shape redaction at the source** — `EventLogMiddleware` already records
   shapes, not contents (`<str:42>`, `***REDACTED***`).
2. **Client Tier-C scan** — before anything is queued, a fail-closed scanner
   drops any event that still matches an IP / cred / host pattern.
3. **Gateway Tier-C reject** — the ingest gateway re-scans and rejects, and
   drops the client IP (it never reaches the analytics backend).

## How it is sent

Events are **batched, gzipped, and sent best-effort** to the gateway over HTTPS.
Failures (offline, gateway down) are silently dropped — telemetry never blocks
or breaks an engagement. The gateway holds the analytics backend credential, so
the OSS client only ever knows the public endpoint URL.

See `telemetry-gateway/README.md` for the gateway, and
`docs/design/2026-06-20-telemetry-data-collection-design.md` for the full design.
