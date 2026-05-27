/**
 * WebSocket-handshake token derivation.
 *
 * Why this exists: HTTP basic auth doesn't apply to a WebSocket upgrade
 * cleanly (browsers can't set arbitrary headers on `new WebSocket()`),
 * so we expose a derived token that the client computes server-side via
 * an authenticated API call, then includes as `?token=...` on the WS URL.
 *
 * Properties:
 *   - The plaintext password is **never** transmitted over the wire as a
 *     WS query string; only an HMAC tag is.
 *   - The bcrypt/scrypt hash itself is **never** transmitted; the tag is
 *     keyed by the hash but doesn't reveal it.
 *   - Comparison is constant-time (`crypto.timingSafeEqual`).
 *
 * The "secret" in the HMAC is the operator's full scrypt hash string. A
 * fixed `WS_TOKEN_LABEL` adds domain separation so this token can't be
 * cross-replayed against any future HMAC use case keyed by the same hash.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

const WS_TOKEN_LABEL = "decepticon.web-auth.ws-token.v1";

/**
 * Derive the WS handshake token from the scrypt-hash string.
 *
 * Returns a lowercase hex string (64 chars from SHA-256).
 */
export function deriveWsToken(scryptHashRaw: string): string {
  return createHmac("sha256", scryptHashRaw).update(WS_TOKEN_LABEL).digest("hex");
}

/**
 * Constant-time comparison of two hex tokens. Returns `false` for any
 * length mismatch (which itself is not a timing leak — the lengths are
 * fixed by the algorithm above; an attacker only learns "wrong length"
 * if they sent an obviously malformed value).
 */
export function tokensEqual(a: string, b: string): boolean {
  if (typeof a !== "string" || typeof b !== "string") return false;
  if (a.length !== b.length) return false;
  // ASCII hex → `Buffer.from` never fails; mismatched chars decode to
  // different bytes, which timingSafeEqual catches in constant time.
  const ab = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

/**
 * Extract a WS auth token from either an `Authorization: Bearer <token>`
 * header or a `?token=<hex>` query parameter on the upgrade URL. Returns
 * the lowercased hex string, or null if no candidate is present.
 *
 * Browsers can't set arbitrary headers on `new WebSocket(url)`, so the
 * query-param transport is the browser-friendly path; non-browser clients
 * (curl, wscat) get the cleaner Authorization header.
 */
export function extractWsToken(authHeader: string | undefined, url: URL): string | null {
  if (authHeader) {
    const m = /^Bearer\s+([A-Fa-f0-9]+)$/.exec(authHeader);
    if (m) return m[1].toLowerCase();
  }
  const q = url.searchParams.get("token");
  if (q && /^[A-Fa-f0-9]+$/.test(q)) return q.toLowerCase();
  return null;
}
