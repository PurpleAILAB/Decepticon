/**
 * Tier-C content scanner — the server-side fail-closed safety net.
 *
 * The client is supposed to sanitize before sending (decision §0: sanitize on
 * the client). This scanner is the *second* line of defense: if a client bug
 * lets a raw IP / credential / host slip into any string value, the gateway
 * rejects the whole batch rather than forward it. Fail-closed, matching the RoE
 * guardrail posture.
 *
 * CRITICAL: a match must NEVER be echoed back to the caller or written to logs
 * — that would itself leak the secret. We return only the *class* that matched.
 */

export interface TierCHit {
  /** Which forbidden class matched — safe to log (no secret value). */
  klass: string;
  /** JSON path to the offending field — structural only, no value. */
  path: string;
}

/**
 * Forbidden patterns (Tier C). Ordered most-specific first so the reported
 * class is the meaningful one. Deliberately conservative: a false *positive*
 * (rejecting a clean batch) is far cheaper than a false negative (leaking a
 * target IP to the maintainer).
 */
const PATTERNS: ReadonlyArray<readonly [string, RegExp]> = [
  ["private_key", /-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----/],
  ["jwt", /\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b/],
  ["aws_access_key", /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/],
  ["email", /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/],
  ["url", /\bhttps?:\/\/[^\s/$.?#][^\s]*/i],
  ["ipv4", /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/],
  ["ipv6", /\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b|\b(?:[A-Fa-f0-9]{1,4}:){1,7}:\b/],
  ["mac", /\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b/],
  ["user_pass", /\b[\w.-]+:[^\s:@/]{4,}@[\w.-]+/],
  // Long opaque blob: base64/hex secret material. 40+ chars with no spaces.
  ["opaque_blob", /\b[A-Za-z0-9+/]{40,}={0,2}\b/],
  // Bare domain/host (e.g. target.example.com). Requires a non-numeric TLD so
  // version strings like "1.1.13" and tokens like "x86_64" never match.
  ["domain", /\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b/i],
];

/**
 * Keys whose values are strict, dotted enums fixed by the schema (e.g.
 * `type: "tool.call"`). They are validated against a closed allow-list upstream
 * and cannot carry user content, so we skip them — otherwise the `domain`
 * pattern false-positives on the legitimate dot in the enum value.
 */
const ENUM_KEYS: ReadonlySet<string> = new Set(["type"]);

/**
 * Recursively scan every string value in `value`. Returns the first hit (the
 * scan short-circuits — we reject the whole batch on any match, so one is
 * enough). Keys are never scanned (they are fixed schema names), only values —
 * except {@link ENUM_KEYS}, whose schema-locked enum values are skipped.
 */
export function scanTierC(value: unknown, path = "$"): TierCHit | null {
  if (typeof value === "string") {
    for (const [klass, re] of PATTERNS) {
      if (re.test(value)) return { klass, path };
    }
    return null;
  }
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      const hit = scanTierC(value[i], `${path}[${i}]`);
      if (hit) return hit;
    }
    return null;
  }
  if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (ENUM_KEYS.has(k)) continue;
      const hit = scanTierC(v, `${path}.${k}`);
      if (hit) return hit;
    }
    return null;
  }
  return null;
}
