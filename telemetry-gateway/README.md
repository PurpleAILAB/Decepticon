# Decepticon Telemetry Gateway (PoC)

The public, unauthenticated **ingest gateway** for OSS maintainer telemetry —
Layer 1 of [`docs/design/2026-06-20-telemetry-data-collection-design.md`](../docs/design/2026-06-20-telemetry-data-collection-design.md).

A Cloudflare Worker that sits between many OSS clients and the maintainer's
analytics backend. It exists to enforce the privacy invariants an analytics backend
cannot, and to hold the backend secret so the OSS client never has to.

> **PoC status.** Working, tested gateway (schema + Tier-C scanner + PostHog
> forward + rate-limit) **plus** a Python client that emits to it: consent
> resolution, sanitizer, batch exporter, and a sink wired into
> `EventLogMiddleware` (`packages/decepticon/decepticon/telemetry/`), the
> `decepticon-cli telemetry` subcommand, and `TELEMETRY.md`. Remaining: MITRE
> tagging at the agent layer (the heatmap source) and production hardening.

## Why a gateway (and not client → a third-party analytics backend directly)

OSS can't ship a write credential — embedding a backend key is a key-leak. The
gateway is the standard fix: the client learns only the public Worker URL; the
gateway holds the secret and forwards server-side. It also lets us:

| Invariant | How the gateway enforces it |
|---|---|
| **Drop client IP** | The user's IP is invisible to PostHog (the *gateway* is the connecting client); we also set `$geoip_disable`. IP is used only transiently as a rate-limit key, never stored or forwarded. |
| **Tier-C never leaks** | Fail-closed content scan (`src/tierc.ts`): if a client bug lets a raw IP / cred / host through, the **whole batch is rejected (422)** — the matched value is never echoed or logged. |
| **Off-contract data dropped** | Strict Zod schema (`src/schema.ts`): unknown envelope/event keys are rejected (400). The schema is a closed allow-list of non-identifying scalar/enum fields. |
| **Abuse cap** | Per-`install_id` rate limit on a public endpoint. |

This mirrors Stacklok ToolHive's design (a security tool with the same threat
model): a maintainer collector receiving only anonymous, identifier-stripped
counts.

## Data flow

```
Decepticon client (URL only, no secret)
   │  POST /v1/telemetry   { Tier-A batch, batched + gzipped }
   ▼
Cloudflare Worker (this)
   │  1. method/size/content-type guards
   │  2. Zod schema validation        → 400
   │  3. Tier-C fail-closed scan       → 422  (never echo the value)
   │  4. rate-limit (install_id+IP)    → 429
   │  5. forward (server-side key)
   ▼
PostHog  /batch/   (funnels, distributions, ATT&CK heatmap — §5 outputs)
```

## Layout

| File | Role |
|---|---|
| `src/schema.ts` | **Canonical Tier-A contract** (Zod). Runtime ingest validation. |
| `schema.json` | Language-neutral mirror (JSON Schema) — the Python client validates against this. Keep in sync with `schema.ts`. |
| `src/tierc.ts` | Fail-closed forbidden-content scanner (IPv4/6, email, URL, host, AWS key, JWT, MAC, user:pass, private key, opaque blob). |
| `src/posthog.ts` | Forwarder to PostHog `/batch/` with privacy hardening. |
| `src/index.ts` | Worker `fetch` handler wiring the pipeline. |
| `test/` | vitest: Tier-C corpus (§9.1 "no leak" gate), schema contract, full handler. |

## Develop & test

```bash
cd telemetry-gateway
npm install
npm run typecheck
npm test
npm run dev          # local Worker at http://localhost:8787
```

## Deploy (maintainer-side)

```bash
npx wrangler secret put POSTHOG_KEY   # PostHog project key — server-only secret
npx wrangler deploy
```

Cost: Cloudflare free tier (100k req/day, scale-to-zero) + PostHog free tier
(1M events/mo) = **$0**. The Worker abstracts the backend, so a later fan-out to
ClickHouse/Grafana needs no client change.

## Schema ↔ contract sync

`src/schema.ts` (Zod) and `schema.json` (JSON Schema) describe the **same** wire
format. `schema.ts` is authoritative for ingest; `schema.json` is what the
Python client should validate against before sending. When you change one,
change the other (a generator can replace the hand-mirror later).

## Next steps (not in this PoC)

1. Python client emitter — reuse `event_log.py` shapes, POST Tier-A batches.
2. Consent CLI — `decepticon telemetry status|off|preview`, honor `DO_NOT_TRACK`.
3. `TELEMETRY.md` — every field, the redaction rules, the endpoint.
4. Tier-B classification/redaction behind `extended` consent.
