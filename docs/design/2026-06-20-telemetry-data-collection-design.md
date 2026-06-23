# Telemetry & Usage Data Collection — Design

> Branch: `claude/decepticon-telemetry-research-5comvf` (2026-06-20).
> Goal: give maintainers visibility into **what users ask the agents to do and
> what the agents actually do**, without ever exfiltrating engagement-sensitive
> content (targets, credentials, client data). Decepticon is a red-team test
> harness, so the privacy bar is higher than for a normal dev tool — prompts and
> tool I/O routinely contain real target IPs, credentials, and client material
> covered by NDA / Rules of Engagement.

## 0. Decisions locked

1. **Sanitize on the client, never on the server.** Raw prompts / tool output
   never leave the user's machine. "Send everything and filter server-side" is
   rejected (the [claude-task-master Sentry incident][cm-sentry] failure mode).
2. **Capture depth = classification + placeholder redaction** (Tier B, see §2).
   Free-text intent is mapped to an enum taxonomy *and* identifier-redacted
   request/command shapes are kept. Local-LLM abstractive summary (option ③) is
   deferred to a later, higher-consent tier.
3. **Maintainer-collection backbone = OpenTelemetry → OTel Collector.** Reuse
   the existing `telemetry/otel.py` OTLP exporter; the maintainer runs one
   Collector that routes to ClickHouse / Langfuse / Grafana.
4. **Opt-in, with `DO_NOT_TRACK` honored.** Tiered consent; a `telemetry
   preview` command shows the exact payload before anything is sent.
5. **LangSmith is NOT the maintainer-collection channel** — it is offered only
   as an optional *bring-your-own* per-user debugging layer (see §6).

## 1. Current state (what already exists)

Decepticon already has the lower half of a telemetry stack — it is local and
deliberately content-free:

| Layer | Location | Behavior |
|---|---|---|
| Event log (JSONL) | `runtime/event_log.py`, `middleware/event_logging.py` → `engagements/<id>/events.jsonl` | `LLM_CALL / TOOL_CALL / TOOL_RESULT / FINDING_CREATED`, **local only** |
| OpenTelemetry (opt-in) | `telemetry/otel.py` (263 lines) | spans `decepticon.engagement / agent_run / tool_call / llm_call`; OTLP exporter; no-op unless `OTEL_ENABLED` |
| Full recording | `runtime/recording.py` | full prompt/output capture, **local only** |
| Knowledge graph | Neo4j | findings / attack chains |

Key existing invariant (`telemetry/otel.py` docstring): *"Prompt text, tool
outputs, credentials, and target URLs are never recorded as span attributes."*
And `EventLogMiddleware` writes **shapes, not contents** (`<str:123>`, redacted
args via `_SENSITIVE_KEY_HINTS`, `event_logging.py:57`).

**What is missing** is (a) a channel that ships *anything* back to maintainers,
and (b) semantic capture of *request intent* and *action meaning* (today's logs
intentionally strip all content). This design adds both, safely.

## 2. Data tiers

| Tier | Nature | Example fields | Sent? | Consent |
|---|---|---|---|---|
| **A. Structural** | non-identifying, always safe | version, OS, agent name, tool name, command binary (`nmap`/`sqlmap`), status, duration, tokens, cost, counts, **MITRE ATT&CK technique IDs**, **CWE/CVE IDs**, finding category | yes (after opt-in) | basic |
| **B. Semantic (sanitized)** | the user's actual goal: request intent + action meaning | request classification, redacted request summary, placeholder-redacted command args (`nmap -sV <IP>`), agent delegation flow | yes | extended |
| **C. Forbidden** | never transmittable | raw prompt, target IP/domain/host, credentials, file contents, tool output, client/org names | **never** | — |

The value the maintainer wants ("what users request / what agents do") lives in
**Tier B**. Making Tier B safe is the whole point of §3.

## 3. Sanitization pipeline (how Tier B is produced)

Runs locally before anything is queued. Two techniques, both enabled by the
locked decision:

### ① Classification (zero free-text)
Map free-text request → enums. Not one character of free text leaves.

```json
{
  "request_intent": "service_enumeration",
  "attack_phase": "reconnaissance",
  "mitre_tactics": ["TA0007"],
  "mitre_techniques": ["T1046"],
  "asset_class": "internal_network",
  "prompt_lang": "ko",
  "prompt_len_bucket": "50-100"
}
```

Implementation: rule/regex first; optional local small-LLM classifier reusing the
agent's existing LLM access.

### ② Placeholder redaction (preserve shape, drop identifiers)
Keep the *structure* of the request/command; replace identifiers with typed
tokens.

```
raw:       "list SMB shares on 10.0.0.5, creds admin:P@ss"
sanitized: "list SMB shares on <IP>, creds <CRED>"

raw cmd:       nmap -sV -p445 10.0.0.5
sanitized cmd: nmap -sV -p445 <IP>
```

Regex set: IPv4/v6, domain/host, URL, email, MAC, AWS/GCP key patterns,
`user:pass`, JWT, hashes, base64 blobs, file paths. Extends the existing
`_SENSITIVE_KEY_HINTS` / `_redact_args` machinery in `event_logging.py:57-107`.

### ③ Local-LLM abstractive summary (deferred)
e.g. *"user requested SMB share enumeration on an internal host"* — richest
research value, but LLM cost + hallucination risk → highest consent tier, not in
the first cut.

## 4. Architecture (two layers, two purposes)

```
[user machine]                                  [maintainer infra]
 Agent run
   │ wrap_model_call / wrap_tool_call (existing middleware hooks)
   ▼
 TelemetryMiddleware ──► Sanitizer (①②) ──► local batch queue
                                               │ batched, gzip, backoff, offline-tolerant
                                               ▼
                                        OTLP/HTTP  ───►  OTel Collector
                                                          (authn, rate-limit, DROP client IP)
                                                          ▼
                                              ClickHouse / Langfuse / Grafana
```

- **Layer 1 — maintainer collection (this design):** OTel Collector backbone +
  local sanitizer. Only identifier-stripped Tier A/B leaves. This is the goal.
- **Layer 2 — per-user debugging (BYO, docs only):** user points LangSmith *or*
  Langfuse at their *own* account via env vars; full content, never reaches the
  maintainer. See §6.

Anonymous identity:
- `install_id`: random UUID minted on first run (not machine/IP derived);
  optional rotation. Used only to correlate sessions.
- engagement id is **hashed** before send (correlatable, not reversible).
- Collector **must drop client IP** (never store/log).

## 5. What maintainers realistically get

After sanitization, with zero personal/client data:

- **Request distribution** — most-requested tasks (recon / exploit / AD / cloud / …).
- **Agent utilization** — which of the 16 agents are used/idle; delegation
  patterns (soundwave → recon → exploit).
- **Tool popularity / failure** — most-called tools, where `status=error`.
- **MITRE ATT&CK coverage** — tactic/technique heatmap of real usage.
- **Funnel / drop-off** — where runs stop after `engagement.start`; HITL
  approve/deny rates.
- **Cost / performance** — tokens/cost/latency per agent; model/provider mix.
- **Quality** — `finding.created` rate, CWE/CVE distribution, retry rate.
- **Environment** — version/OS distribution (support & upgrade policy).

## 6. Why not LangSmith as the collection channel?

Decepticon is LangGraph+LangChain, so LangSmith auto-traces the full agent run
with one env var (`LANGSMITH_TRACING=true`). Lowest *dev effort* — but wrong tool
for *maintainer collection from OSS users*:

| Criterion | LangSmith as collection channel |
|---|---|
| Default capture | ❌ captures full prompts + tool I/O by default = targets, creds, client data (Tier C). `hide_inputs/outputs` is a fragile send-then-mask blocklist — same anti-pattern as the Sentry incident. |
| Self-hosting | ❌ self-host is Enterprise-only, closed source. Routing OSS users' pentest data to a third-party analytics service breaks the Apache-2.0 / self-hosted posture. |
| Collection model | ❌ designed for one org tracing its own agents; many-users→one-maintainer would require a shared API key shipped in the OSS (key-leak problem), and gives users no control. |
| Data shape | ❌ trace debugging, not aggregate product analytics (funnels, distributions). |

**Where LangSmith *is* efficient:** a user pointing their *own* LangSmith (or
self-hostable Langfuse) at their *own* runs for debugging — full content is an
asset there, and it is one env var. We document this as Layer 2 (BYO), not as the
maintainer pipe. Since OTel, LangSmith, and Langfuse all speak OTLP, Layer 1's
OTel backbone and Layer 2's BYO observability coexist cleanly.

## 7. Consent model

Opt-in (security/sensitive tool → opt-out is too risky):

```bash
# first-run prompt (once):
#   "Send anonymous usage stats? Prompt text / targets / credentials are
#    NEVER transmitted. Details: TELEMETRY.md  [y/N]"

DECEPTICON_TELEMETRY=off|basic|extended   # off / Tier A / Tier A+B
DO_NOT_TRACK=1                            # standard; forces off
DECEPTICON_TELEMETRY_ENDPOINT=...         # users may self-route
```

- Tiered consent (Tier A only / through B / later ③).
- `decepticon telemetry status|off|preview` — **`preview` prints the exact
  payload that would be sent** (transparency; cf. Go's transparent telemetry).
- `TELEMETRY.md` documents every collected field, the redaction rules, and the
  endpoint.

## 8. Implementation mapping (real files)

| Work | File | Notes |
|---|---|---|
| New middleware | `middleware/telemetry.py` | mirror `EventLogMiddleware` structure; sanitize then export in `wrap_model_call` / `wrap_tool_call` |
| Sanitizer | `telemetry/sanitizer.py` | ① classify + ② regex redact; reuse `_redact_args` / `_SENSITIVE_KEY_HINTS` (`event_logging.py:57-107`) |
| Tier-B spans | `telemetry/otel.py` | add semantic attrs (`request_intent`, `mitre.technique`, …) to existing spans |
| Exporter | `telemetry/exporter.py` | batch queue + gzip OTLP + backoff retry + offline buffer |
| Slot registration | `agents/middleware_slots.py` | add `TelemetryMiddleware` to the 13-slot registry |
| Consent CLI | `cli/__main__.py` | first-run consent + `telemetry` subcommand |
| Web analytics (optional) | `clients/web/` (Next.js) | PostHog SDK for dashboard usage |
| Docs | `TELEMETRY.md` | collected fields, consent, `DO_NOT_TRACK` |

Schema reuses the existing `EventType` enum (`event_log.py:87`); add
`telemetry.request` and `telemetry.action` for consistency.

## 9. Sequencing

1. Sanitizer + unit tests (regex corpus of IPs/creds/hosts → asserts no leak).
2. `TelemetryMiddleware` (Tier A only) wired through the slot registry.
3. Exporter + OTel Collector reference config (maintainer side).
4. Consent CLI + `telemetry preview` + `TELEMETRY.md`.
5. Tier B classification/redaction behind `extended` consent.
6. (Later) option ③ local-LLM summary; PostHog for web product analytics.

## References

- Transparent telemetry for open source (Go): research.swtch.com/telemetry-intro
- OpenTelemetry tools 2026 — dash0.com/comparisons/best-opentelemetry-tools
- Agent observability (LangSmith/Langfuse/Arize) 2026 — digitalapplied.com
- Langfuse self-hosting / OTLP — langfuse.com/faq/all/langsmith-alternative
- PostHog open source — cotera.co/articles/posthog-open-source-analytics
- GitHub CLI opt-out telemetry (2026-04) — github.blog/changelog
- [Sentry full-prompt capture anti-pattern][cm-sentry] — github.com/eyaltoledano/claude-task-master/issues/1681

[cm-sentry]: https://github.com/eyaltoledano/claude-task-master/issues/1681
