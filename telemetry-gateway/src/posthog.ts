/**
 * PostHog forwarder.
 *
 * The gateway is the only party that holds the PostHog project key (a server
 * secret — never shipped in the OSS client). Each validated batch is fanned out
 * to PostHog's `/batch/` capture endpoint, one PostHog event per telemetry
 * event, keyed by the anonymous `install_id`.
 *
 * Privacy: the user's IP is already invisible to PostHog because the *gateway*
 * is the connecting client. We additionally set `$geoip_disable` and never
 * attach any IP property, so no geo enrichment happens server-side either.
 */
import type { TelemetryBatch } from "./schema";

export interface PostHogEnv {
  POSTHOG_KEY: string;
  POSTHOG_HOST?: string;
}

/** Injectable for tests; defaults to the global fetch. */
export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

const DEFAULT_HOST = "https://us.i.posthog.com";

export async function forwardToPostHog(
  batch: TelemetryBatch,
  env: PostHogEnv,
  fetchImpl: FetchLike = fetch,
): Promise<Response> {
  // Strip trailing slashes without a regex (avoids the ReDoS surface CodeQL
  // flags on env-derived input).
  let host = env.POSTHOG_HOST ?? DEFAULT_HOST;
  while (host.endsWith("/")) host = host.slice(0, -1);

  const phBatch = batch.events.map((ev) => {
    const { type, ts, ...props } = ev;
    return {
      event: type,
      distinct_id: batch.install_id,
      timestamp: new Date(ts * 1000).toISOString(),
      properties: {
        ...props,
        // Envelope context, flattened onto every event for easy slicing.
        decepticon_version: batch.client.decepticon_version,
        os: batch.client.os,
        arch: batch.client.arch,
        py: batch.client.py,
        tier: batch.tier,
        // Privacy hardening — no IP, no geo enrichment.
        $geoip_disable: true,
        $process_person_profile: false,
      },
    };
  });

  return fetchImpl(`${host}/batch/`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ api_key: env.POSTHOG_KEY, batch: phBatch }),
  });
}
