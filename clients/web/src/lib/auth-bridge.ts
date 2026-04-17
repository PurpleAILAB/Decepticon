import { getEE, hasEE } from "@/lib/ee";
import type { EESession } from "@/lib/ee";

/**
 * Auth bridge — abstracts authentication for OSS/SaaS modes.
 *
 * - SaaS (EE installed): Delegates to EE auth module (NextAuth, SSO, etc.)
 * - OSS (no EE): Returns a default local session — no auth required.
 */

export class AuthError extends Error {
  constructor(message = "Unauthorized") {
    super(message);
    this.name = "AuthError";
  }
}

export interface AuthResult {
  userId: string;
  session: EESession | null;
}

/**
 * Require authentication. In SaaS mode, returns the authenticated user's session
 * or throws AuthError. In OSS mode, returns a default local user (no auth check).
 *
 * Guard: if EE is installed but auth is not wired, treat as a misconfiguration
 * and throw rather than silently falling through to "local" mode.
 */
export async function requireAuth(): Promise<AuthResult> {
  const ee = getEE();
  if (ee.auth) {
    const session = await ee.auth.getSession();
    if (!session) {
      throw new AuthError();
    }
    return { userId: session.user.id, session };
  }
  // Guard: EE is present but auth is not configured — fail-fast
  if (hasEE() && !ee.auth) {
    throw new AuthError(
      "@decepticon/ee is installed but auth is not configured. " +
      "Wire the auth field in the EE package or remove EE for OSS mode."
    );
  }
  // OSS mode — no authentication, single local user
  return { userId: "local", session: null };
}

/**
 * Get the current session if available. Returns null in OSS mode.
 */
export async function getSession(): Promise<EESession | null> {
  const ee = getEE();
  if (ee.auth) {
    return ee.auth.getSession();
  }
  return null;
}

/**
 * Check if authentication is enabled (EE auth module present).
 */
export function isAuthEnabled(): boolean {
  return !!getEE().auth;
}
