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

- **`basic` → Tier A (structural ground truth, always safe):** event type, agent
  name, tool name (e.g. `nmap`), normalized status, bucketed sizes, token counts,
  model id — **plus the classification the engagement itself produces**, derived
  from the `Finding` model and OPPLAN tracker (not inferred from your prompt):

  | Event | Fields collected | Never collected |
  |---|---|---|
  | `finding.created` | `severity`, `cwe`, `mitre_techniques`, `phase`, `confidence`, `detected` (purple-team), `agent` | finding title/description, `affected_target`, evidence, PoC |
  | `opplan.update` | `phase` (recon→…→exfiltration), `status_objective` (pending/blocked/…) | objective title/notes |
  | `tool.result` | `tool`, `status`, `output_bucket` | tool output |

  This is how maintainers learn **what the tool actually finds and where
  engagements stall** (e.g. CWE/severity distribution = what it detects; `blocked`
  clusters at a phase = where it fails) — entirely from the agent's structured
  artifacts, never from prompt text.

- **`extended` → Tier A + B:** additionally your **HITL decisions** —
  `hitl.decision` `{tool, decision: approve/deny/edit, agent}` — which actions you
  do and don't let the agent take. Enable with
  `decepticon-cli telemetry enable extended` (it prints the disclosure first).

  **Consent boundary:** findings/phases describe what the *agent* did and are
  non-identifying. The *target's* data — IPs, hosts, domains, credentials,
  finding descriptions — is never sent, because a third party's data is not yours
  to consent away.

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
