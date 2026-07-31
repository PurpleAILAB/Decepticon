# Decepticon Telemetry

Decepticon can send **anonymous usage telemetry** to help maintainers see what
users ask the agents to do and what the agents actually do. Decepticon is
free/OSS; this sharing helps fund and improve it. It is **opt-out** — the
onboard wizard asks for consent (default yes) and you can turn it off at any
time — and designed for a red-team threat model: **raw prompts, targets,
credentials, and tool output are never transmitted.**

## TL;DR

- **On by default for consenting users (opt-out).** The onboard wizard asks
  during setup (default yes), writing `DECEPTICON_TELEMETRY=research`. Existing
  users are re-asked once at `decepticon start` after this policy change.
- **Turn it off anytime:** set `DECEPTICON_TELEMETRY=off` (or `basic`) in
  `~/.decepticon/.env`, run `decepticon-cli telemetry off`, or `DO_NOT_TRACK=1`.
- **Nothing is sent** without a `DECEPTICON_TELEMETRY_ENDPOINT` (shipped in the
  `.env` template; backfilled into existing installs on update).
- **See exactly what would be sent:** `decepticon-cli telemetry preview`.

## Controls

| Variable / command | Effect |
|---|---|
| `DECEPTICON_TELEMETRY=off\|basic\|research` | consent mode (template default `research`; unset ⇒ `off`) |
| `DO_NOT_TRACK=1` | standard kill switch — forces `off` |
| `BENCHMARK_MODE=1` | forces `off` — benchmark prompts are harness-generated, not user activity |
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

- **`research` → the reasoning corpus:** additionally the red-team **reasoning**
  — your objectives, the agent's chain-of-thought / tactic rationale, the commands
  it runs, and the observations — captured **as-is** so the attacker reasoning is
  preserved for training future autonomous red-team agents. The chain-of-thought
  is whatever the model actually produced (extended-thinking blocks included);
  harness-injected `<system-reminder>` blocks are stripped from your turns, so
  what is recorded as human input is what you wrote. **Target identifiers
  are MASKED** (`10.0.0.5` → `<HOST_1>`, creds → `<CRED_1>`) so the reasoning stays
  intact but no real target/credential is shared. Enable with
  `decepticon-cli telemetry enable research` (it prints the disclosure first).

  **Consent boundary:** the agent's reasoning is yours to share. The *target's*
  data is not yours to consent away, so it is masked even here.

  **What masking actually guarantees — and what it does not.** Masking is
  pattern-based plus whatever your engagement declared. It reliably removes
  **structured identifiers** (IPs, MACs, emails, URLs, private keys, JWTs, cloud
  access keys) and the **identity your RoE declares** (client organization,
  engagement name/slug, authorizer, in-scope hosts) — which is why filling in
  the client field when the RoE is created matters.

  It is **not** a guarantee against everything. A company or product name typed
  into free prose, a credential phrased in a language the patterns do not cover,
  or a distinctive description of an asset can survive. Published research also
  shows that LLMs can re-identify subjects from context alone even after
  identifiers are removed. Treat `research` as *"identifiers are stripped and
  the corpus is handled as sensitive"*, not as anonymization. If your engagement
  cannot tolerate that, use `basic` or `off`.

One extra event type, `telemetry.drop`, reports how many events Decepticon's own
fail-closed scanner **discarded** before sending, counted by class (e.g.
`{"category": "ipv4", "count": 3}`). It carries the class and a number only —
never the content that was dropped — and exists so silent over-dropping is
visible rather than mistaken for an idle install.

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

### Example — a `research` trajectory (masked, role-labeled, ordered)

Each step carries a **`role`** (human input / agent output / tool execution), a
per-engagement **`session_id`**, and a monotonic **`step`** — so the whole
trajectory reconstructs in order (`WHERE session_id = X ORDER BY step`) into the
turn sequence a training pipeline needs. Identifiers are masked throughout:

```json
{
  "schema_version": "1.0",
  "tier": "R",
  "install_id": "1e9a73a6-…",
  "client": { "decepticon_version": "1.1.13", "os": "linux" },
  "events": [
    { "type": "trajectory.step", "session_id": "a1b2c3d4e5f60718", "step": 0,
      "role": "human", "agent": "decepticon", "text": "Objective: own the host at <HOST_1>" },
    { "type": "trajectory.step", "session_id": "a1b2c3d4e5f60718", "step": 1,
      "role": "agent", "agent": "exploit",
      "text": "the login at <DOMAIN_1> on <HOST_1> looks injectable — try UNION-based SQLi" },
    { "type": "trajectory.step", "session_id": "a1b2c3d4e5f60718", "step": 2,
      "role": "tool", "agent": "exploit", "tool": "bash",
      "args_text": "sqlmap -u <URL_1> --batch", "observation": "dumped 12 rows from <HOST_1>" }
  ]
}
```

The reasoning structure is intact (training value preserved); `<HOST_1>` is the
same placeholder every time that host recurs in the session, but the real target
/ credentials never leave the machine. `session_id` is a hash (the engagement
name may carry a client/org name, so it is never sent raw).

## What is blocked before sending (Tier C)

Target IPs / domains / hosts, credentials, keys and tokens are blocked by
**three layers**:

1. **Shape redaction at the source** — `EventLogMiddleware` records shapes, not
   contents (`<str:42>`, `***REDACTED***`), for the `basic` tier.
2. **Client Tier-C scan** — before anything is queued, a fail-closed scanner
   drops any event still matching an IP / cred / host pattern. Drops are
   reported as a `telemetry.drop` count, never as content.
3. **Gateway Tier-C reject** — the ingest gateway re-scans and rejects, and
   drops your IP (it never reaches the analytics backend).

Layers 2 and 3 are **pattern-based**, which bounds what they can promise: see
the `research` tier notes above for what survives. They are a floor, not
anonymization.

## Where it goes, and for how long

- **Recipient:** PurpleAILAB, the Decepticon maintainers. Batches go to a
  Cloudflare Worker we operate, which forwards to our PostHog project. The
  Worker never records your IP and disables geo-enrichment.
- **Purpose:** improving Decepticon, and — for the `research` tier — building a
  training corpus for future autonomous red-team agents.
- **Identity:** a random `install_id` (never machine- or IP-derived) plus a
  per-engagement `session_id` that is a salted hash. Neither is linked to an
  account; we cannot contact you from telemetry alone.
- **Retention:** data is retained under our analytics backend's default
  retention. A specific published retention window and a self-serve deletion
  path are **not yet in place** — until they are, the reliable control is
  turning telemetry off (`DECEPTICON_TELEMETRY=off`, `DO_NOT_TRACK=1`, or
  `decepticon-cli telemetry off`), which takes effect immediately. If you need
  data already sent to be removed, open an issue with your `install_id`
  (`decepticon-cli telemetry status` prints it).

## How it is sent

Events are **batched, gzipped, and sent best-effort** to the gateway over HTTPS.
Failures (offline, gateway down) are silently dropped — telemetry never blocks
or breaks an engagement. The gateway holds the analytics backend credential, so
the OSS client only ever knows the public endpoint URL.

See `telemetry-gateway/README.md` for the gateway, and
`docs/design/2026-06-20-telemetry-data-collection-design.md` for the full design.
