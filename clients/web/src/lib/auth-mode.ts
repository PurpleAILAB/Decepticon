/**
 * Auth-mode parser for the web dashboard + terminal WebSocket.
 *
 * The default is **unchanged** from upstream Decepticon: no authentication.
 * That's fine on localhost, but exposing the ports off-host (port-forward,
 * reverse proxy, etc.) hands an unauthenticated agent driver to the network.
 *
 * Operators can opt in via the `DECEPTICON_WEB_AUTH` env var:
 *
 *   - `none`                    — today's behavior (default).
 *   - `password:<scrypt>`       — HTTP basic auth on web routes; WebSocket
 *                                 handshake requires a token derived from
 *                                 the same scrypt hash via HMAC-SHA256.
 *   - `disable-bind-public`     — server hard-fails startup if it would
 *                                 bind to anything other than loopback.
 *
 * The scrypt format is `scrypt$<N>$<r>$<p>$<base64-salt>$<base64-key>` —
 * see `hashPassword()` / `verifyPassword()` in this file for the helpers,
 * and `SECURITY.md` for the operator-facing recipe.
 *
 * We use `node:crypto.scryptSync` rather than bringing in `bcrypt`:
 *   - no new native-dep build at install time
 *   - scrypt is a well-respected, memory-hard KDF (RFC 7914)
 *   - implementation is in-tree and auditable
 *
 * Malformed env values **throw at startup** rather than silently degrading
 * to "no auth" — fail loud, never silently expose.
 */
import { scryptSync, timingSafeEqual, randomBytes } from "node:crypto";

export type AuthMode =
  | { kind: "none" }
  | { kind: "password"; hash: ScryptHash }
  | { kind: "disable-bind-public" };

export interface ScryptHash {
  /** raw `scrypt$N$r$p$salt$key` string, used as the WS-token-derivation secret */
  raw: string;
  N: number;
  r: number;
  p: number;
  salt: Buffer;
  key: Buffer;
}

const SCRYPT_PREFIX = "scrypt$";

/**
 * Parse `DECEPTICON_WEB_AUTH`. Defaults to `{kind:"none"}` when unset/empty
 * so existing local-only deployments keep working without any config.
 *
 * Throws on malformed input — startup aborts rather than silently
 * downgrading to no-auth.
 */
export function parseAuthMode(raw: string | undefined): AuthMode {
  if (raw === undefined || raw.trim() === "" || raw === "none") {
    return { kind: "none" };
  }
  if (raw === "disable-bind-public") {
    return { kind: "disable-bind-public" };
  }
  if (raw.startsWith("password:")) {
    const hashStr = raw.slice("password:".length);
    return { kind: "password", hash: parseScryptHash(hashStr) };
  }
  throw new Error(
    `DECEPTICON_WEB_AUTH must be one of: "none" | "password:<scrypt-hash>" | "disable-bind-public". Got: ${truncate(raw)}`,
  );
}

/**
 * Parse a `scrypt$N$r$p$salt$key` string. Throws on malformed input.
 */
export function parseScryptHash(s: string): ScryptHash {
  if (!s.startsWith(SCRYPT_PREFIX)) {
    throw new Error(
      `DECEPTICON_WEB_AUTH=password:<hash> requires an scrypt hash starting with "scrypt$N$r$p$salt$key". Got: ${truncate(s)}`,
    );
  }
  const parts = s.split("$");
  // [ "scrypt", N, r, p, salt, key ]
  if (parts.length !== 6) {
    throw new Error(
      `Malformed scrypt hash — expected 6 \`$\`-separated fields, got ${parts.length}.`,
    );
  }
  const [, NStr, rStr, pStr, saltB64, keyB64] = parts;
  const N = Number.parseInt(NStr, 10);
  const r = Number.parseInt(rStr, 10);
  const p = Number.parseInt(pStr, 10);
  if (!Number.isInteger(N) || N <= 0 || (N & (N - 1)) !== 0) {
    throw new Error(`scrypt N must be a power of two, got: ${NStr}`);
  }
  if (!Number.isInteger(r) || r <= 0) {
    throw new Error(`scrypt r must be a positive integer, got: ${rStr}`);
  }
  if (!Number.isInteger(p) || p <= 0) {
    throw new Error(`scrypt p must be a positive integer, got: ${pStr}`);
  }
  let salt: Buffer;
  let key: Buffer;
  try {
    salt = Buffer.from(saltB64, "base64");
    key = Buffer.from(keyB64, "base64");
  } catch {
    throw new Error("scrypt salt/key must be base64-encoded.");
  }
  if (salt.length === 0 || key.length === 0) {
    throw new Error("scrypt salt and key must be non-empty.");
  }
  return { raw: s, N, r, p, salt, key };
}

/**
 * Hash a plaintext password for the operator. Used by an out-of-band CLI
 * recipe (see SECURITY.md). Not called from the request hot path.
 */
export function hashPassword(
  plaintext: string,
  opts: { N?: number; r?: number; p?: number; keyLen?: number; salt?: Buffer } = {},
): string {
  const N = opts.N ?? 16384;
  const r = opts.r ?? 8;
  const p = opts.p ?? 1;
  const keyLen = opts.keyLen ?? 32;
  const salt = opts.salt ?? randomBytes(16);
  // scryptSync needs `maxmem` raised when N is large.
  const maxmem = 128 * N * r * 2;
  const key = scryptSync(plaintext, salt, keyLen, { N, r, p, maxmem });
  return `scrypt$${N}$${r}$${p}$${salt.toString("base64")}$${key.toString("base64")}`;
}

/**
 * Constant-time password verification against a parsed scrypt hash.
 */
export function verifyPassword(plaintext: string, hash: ScryptHash): boolean {
  const maxmem = 128 * hash.N * hash.r * 2;
  const derived = scryptSync(plaintext, hash.salt, hash.key.length, {
    N: hash.N,
    r: hash.r,
    p: hash.p,
    maxmem,
  });
  if (derived.length !== hash.key.length) return false;
  return timingSafeEqual(derived, hash.key);
}

function truncate(s: string): string {
  return s.length > 32 ? `${s.slice(0, 32)}…` : s;
}
