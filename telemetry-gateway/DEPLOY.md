# Deploying the Telemetry Gateway (maintainer runbook)

One-time setup. The gateway is persistent infra — deploy it **once**, then bake
its URL into the OSS release. After that, every opted-in user sends to it.

Cost: Cloudflare Workers free tier (100k req/day, scale-to-zero) + PostHog free
tier (1M events/mo) = **$0**.

## 1. PostHog project (the dashboard where you read the data)

1. Sign up at <https://posthog.com> (cloud) — or self-host.
2. Create a project. Copy its **Project API Key** (`phc_...`). This is a
   write-only ingestion key; it is safe to hold on the server (the Worker), and
   it never ships in the OSS client.
3. Note your region host:
   - US cloud → `https://us.i.posthog.com` (the default in `wrangler.toml`)
   - EU cloud → `https://eu.i.posthog.com` (edit `[vars] POSTHOG_HOST`)
   - self-host → your URL

## 2. Deploy the Worker (Cloudflare)

From `telemetry-gateway/`:

```bash
npm install
npx wrangler login                 # interactive: authorizes your Cloudflare account
npx wrangler secret put POSTHOG_KEY   # paste the phc_... key (stored encrypted, server-side)
npx wrangler deploy
```

`deploy` prints the public URL, e.g.
`https://decepticon-telemetry-gateway.<account>.workers.dev`.

> Wrangler v3 warns the bundled runtime caps the compatibility date — harmless.
> `npm i -D wrangler@4` removes the warning if you prefer.

## 3. Verify the live gateway

```bash
URL=https://decepticon-telemetry-gateway.<account>.workers.dev

# health
curl -s "$URL/"            # -> {"service":"decepticon-telemetry-gateway","ok":true}

# a clean masked event is accepted (202) and lands in PostHog
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$URL/v1/telemetry" \
  -H 'content-type: application/json' \
  -d '{"schema_version":"1.0","tier":"A","install_id":"00000000-0000-4000-8000-000000000000","client":{"decepticon_version":"0.0.0","os":"linux"},"events":[{"type":"tool.call","ts":1,"tool":"nmap"}]}'
# -> 202

# a raw target IP is REJECTED (422) and never forwarded
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$URL/v1/telemetry" \
  -H 'content-type: application/json' \
  -d '{"schema_version":"1.0","tier":"R","install_id":"00000000-0000-4000-8000-000000000000","client":{"decepticon_version":"0.0.0","os":"linux"},"events":[{"type":"trajectory.step","ts":1,"reasoning":"exploit 10.0.0.5"}]}'
# -> 422
```

Then open the PostHog project — the `tool.call` event should appear.

## 4. Ship it in the OSS release

Set the deployed URL as the default endpoint so the next release collects from
opted-in users. In `clients/launcher/internal/config/env.example`:

```ini
DECEPTICON_TELEMETRY_ENDPOINT=https://decepticon-telemetry-gateway.<account>.workers.dev/v1/telemetry
```

(Leave `DECEPTICON_TELEMETRY=off` — users opt in via the onboard wizard.) Commit,
then tag the release as usual. From that release on, users who pick `basic` or
`research` at onboard will send identifier-masked telemetry to your gateway.

## Rotating / disabling

- Rotate the PostHog key: `npx wrangler secret put POSTHOG_KEY` again.
- Take the gateway down: `npx wrangler delete` (clients with the endpoint set
  will simply fail to send — telemetry is best-effort and never blocks a run).
