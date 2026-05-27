/**
 * Auth bridge — single-user local deploy, with optional opt-in auth.
 *
 * Decepticon is self-hosted and single-user by default. The historical
 * behavior is "every request resolves to the local user" — no
 * authentication at all. That stays the default.
 *
 * Operators who expose the dashboard off-host can opt in via the
 * `DECEPTICON_WEB_AUTH` env var (see ./auth-mode.ts). When set to
 * `password:<scrypt>`, this module enforces HTTP basic auth on the
 * request headers; missing or wrong creds raise `AuthError`, which the
 * route handlers already translate into a 401.
 */

import { parseAuthMode, verifyPassword, type AuthMode } from "./auth-mode";

export class AuthError extends Error {
  constructor(message = "Unauthorized") {
    super(message);
    this.name = "AuthError";
  }
}

export interface AuthResult {
  userId: string;
  session: null;
}

// Parse once at module load. A bad env value should fail loud at startup
// rather than silently degrading to no-auth at request time.
let cachedMode: AuthMode | undefined;

function getMode(): AuthMode {
  if (cachedMode === undefined) {
    cachedMode = parseAuthMode(process.env.DECEPTICON_WEB_AUTH);
  }
  return cachedMode;
}

/** Test-only — reset the cached mode so tests can flip `DECEPTICON_WEB_AUTH`. */
export function __resetAuthModeCacheForTests(): void {
  cachedMode = undefined;
}

/**
 * The basic-auth header parser. Accepts the request's `Authorization`
 * header value (or undefined). Returns `[user, pass]` or `null`.
 */
function parseBasicAuthHeader(header: string | null | undefined): [string, string] | null {
  if (!header) return null;
  const m = /^Basic\s+([A-Za-z0-9+/=]+)$/.exec(header);
  if (!m) return null;
  let decoded: string;
  try {
    decoded = Buffer.from(m[1], "base64").toString("utf8");
  } catch {
    return null;
  }
  const i = decoded.indexOf(":");
  if (i < 0) return null;
  return [decoded.slice(0, i), decoded.slice(i + 1)];
}

/**
 * Lazy import of `next/headers`. We avoid a static import so this module
 * stays loadable in plain Node (e.g. vitest) outside the Next.js request
 * context.
 */
async function readNextAuthHeader(): Promise<string | null> {
  try {
    const mod = await import("next/headers");
    // next/headers `headers()` may be sync or async depending on Next version.
    // In Next 15+ it's async; we await defensively.
    const h = await (mod.headers as () => Promise<Headers> | Headers)();
    return h.get("authorization");
  } catch {
    return null;
  }
}

/**
 * Authenticate the current request.
 *
 * - In `none` mode: returns the local user (today's behavior).
 * - In `password` mode: pulls the `Authorization: Basic ...` header from
 *   the current Next.js request context (`next/headers`), or accepts an
 *   explicit `Headers`/`Request` passed by the caller. Throws AuthError
 *   on missing / wrong credentials.
 * - In `disable-bind-public` mode: behaves like `none` at the auth
 *   layer; the bind restriction is enforced at server startup.
 */
export async function requireAuth(
  reqOrHeaders?: Request | Headers | { headers?: Headers | { get?(k: string): string | null } },
): Promise<AuthResult> {
  const mode = getMode();
  if (mode.kind !== "password") {
    return { userId: "local", session: null };
  }

  // Resolve an Authorization header from the caller-supplied source first,
  // falling back to `next/headers` so existing callers like
  // `await requireAuth()` keep working.
  let authHeader: string | null = null;
  if (reqOrHeaders) {
    if (reqOrHeaders instanceof Request) {
      authHeader = reqOrHeaders.headers.get("authorization");
    } else if (reqOrHeaders instanceof Headers) {
      authHeader = reqOrHeaders.get("authorization");
    } else if (reqOrHeaders.headers) {
      const h = reqOrHeaders.headers;
      if (h instanceof Headers) authHeader = h.get("authorization");
      else if (typeof h.get === "function") authHeader = h.get("authorization");
    }
  }
  if (!authHeader) {
    authHeader = await readNextAuthHeader();
  }

  const creds = parseBasicAuthHeader(authHeader);
  if (!creds) {
    throw new AuthError("Missing or malformed Authorization header");
  }
  const [, password] = creds;
  if (!verifyPassword(password, mode.hash)) {
    throw new AuthError("Invalid credentials");
  }
  return { userId: "local", session: null };
}

export async function getSession(): Promise<null> {
  return null;
}

/**
 * `true` when the operator has opted into password auth. Used by UI
 * code that wants to show / hide a login affordance — does **not**
 * affect server-side enforcement (that's `requireAuth`).
 */
export function isAuthEnabled(): boolean {
  return getMode().kind === "password";
}

/** Test-only escape hatch — returns the parsed mode without exposing the cache var. */
export function __getAuthModeForTests(): AuthMode {
  return getMode();
}
