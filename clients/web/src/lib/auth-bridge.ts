/**
 * Auth bridge — single-user local deploy.
 *
 * Decepticon is self-hosted and single-user. There is no authentication
 * system; every request resolves to the local user.
 */

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

export async function requireAuth(): Promise<AuthResult> {
  return { userId: "local", session: null };
}

export async function getSession(): Promise<null> {
  return null;
}

export function isAuthEnabled(): boolean {
  return false;
}
