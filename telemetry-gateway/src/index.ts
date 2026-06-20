/**
 * Decepticon telemetry gateway — Cloudflare Worker.
 *
 * The single public, unauthenticated ingest endpoint for OSS maintainer
 * collection (design doc §4, Layer 1). It holds the PostHog secret so the OSS
 * client never has to, and enforces the privacy invariants the SaaS backend
 * cannot:
 *
 *   1. drop the client IP        — never read into the forwarded payload
 *   2. validate the Tier-A schema — reject anything off-contract (400)
 *   3. Tier-C content scan        — fail-closed reject on raw IP/cred/host (422)
 *   4. rate-limit                 — per install_id, abuse cap on a public endpoint
 *   5. forward to PostHog         — server-side key, anonymous distinct_id
 *
 * Cost: runs on Cloudflare's free tier (100k req/day), scale-to-zero, $0.
 */
import { forwardToPostHog, type PostHogEnv } from "./posthog";
import { scanTierC } from "./tierc";
import { TelemetryBatch } from "./schema";

interface RateLimiter {
  limit(opts: { key: string }): Promise<{ success: boolean }>;
}

export interface Env extends PostHogEnv {
  /** Optional Cloudflare rate-limiting binding; ingest is unmetered if absent. */
  RATE_LIMITER?: RateLimiter;
  /** Max request body in bytes (default 256 KiB). */
  MAX_BODY_BYTES?: string;
  /** Ingest path (default "/v1/telemetry"). */
  TELEMETRY_PATH?: string;
}

const DEFAULT_PATH = "/v1/telemetry";
const DEFAULT_MAX_BODY = 256 * 1024;

function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = env.TELEMETRY_PATH ?? DEFAULT_PATH;

    // Health check.
    if (request.method === "GET" && url.pathname === "/") {
      return json(200, { service: "decepticon-telemetry-gateway", ok: true });
    }

    if (url.pathname !== path) return json(404, { error: "not_found" });
    if (request.method !== "POST") return json(405, { error: "method_not_allowed" });

    const ctype = request.headers.get("content-type") ?? "";
    if (!ctype.includes("application/json")) {
      return json(415, { error: "unsupported_media_type" });
    }

    // Body-size cap. We read as text with an explicit ceiling so a hostile
    // client cannot stream an unbounded body through the free tier.
    const maxBody = Number(env.MAX_BODY_BYTES ?? DEFAULT_MAX_BODY);
    const declared = Number(request.headers.get("content-length") ?? "0");
    if (declared > maxBody) return json(413, { error: "payload_too_large" });

    let raw: string;
    try {
      raw = await request.text();
    } catch {
      return json(400, { error: "unreadable_body" });
    }
    if (raw.length > maxBody) return json(413, { error: "payload_too_large" });

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return json(400, { error: "invalid_json" });
    }

    // Schema validation — reject anything off the Tier-A allow-list.
    const result = TelemetryBatch.safeParse(parsed);
    if (!result.success) {
      // Report which fields failed (paths only) — never echo values.
      const issues = result.error.issues.slice(0, 8).map((i) => ({
        path: i.path.join("."),
        code: i.code,
      }));
      return json(400, { error: "schema_validation_failed", issues });
    }
    const batch = result.data;

    // Tier-C fail-closed scan over the variable event content. Envelope ids are
    // already format-locked by the schema, so we scan only `events`.
    const hit = scanTierC(batch.events, "$.events");
    if (hit) {
      // Class + path only. The offending VALUE is deliberately not returned or
      // logged — surfacing it would itself leak the secret.
      return json(422, { error: "tier_c_content_rejected", klass: hit.klass, path: hit.path });
    }

    // Rate-limit per anonymous install. The client IP is used transiently as a
    // secondary key but is NEVER stored or forwarded.
    if (env.RATE_LIMITER) {
      const ip = request.headers.get("cf-connecting-ip") ?? "noip";
      const { success } = await env.RATE_LIMITER.limit({ key: `${batch.install_id}:${ip}` });
      if (!success) return json(429, { error: "rate_limited" });
    }

    // Forward. Map PostHog failures to 502 without leaking upstream detail.
    let upstream: Response;
    try {
      upstream = await forwardToPostHog(batch, env);
    } catch {
      return json(502, { error: "upstream_unavailable" });
    }
    if (!upstream.ok) return json(502, { error: "upstream_error", status: upstream.status });

    return json(202, { accepted: batch.events.length });
  },
};
