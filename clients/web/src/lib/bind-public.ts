/**
 * Loopback-only bind enforcement.
 *
 * `DECEPTICON_WEB_AUTH=disable-bind-public` is the "defense in depth"
 * mode: even if the operator's compose / start script accidentally binds
 * to `0.0.0.0`, the process refuses to start. This module exposes a tiny
 * recognizer for "is this a loopback hostname / address?" and a helper
 * that throws on anything else.
 *
 * Loopback patterns recognized:
 *   - `127.0.0.0/8` (any IPv4 loopback, but the common ones are 127.0.0.1)
 *   - `::1` (canonical IPv6 loopback, with or without zone id)
 *   - `localhost`
 *
 * Anything else — including the empty string (which `node`'s `listen`
 * treats as "all interfaces"), `0.0.0.0`, `::`, and any concrete LAN /
 * public IP — is rejected.
 */

const LOOPBACK_NAMES = new Set(["localhost"]);

export function isLoopbackHost(host: string): boolean {
  if (!host) return false; // empty == all-interfaces
  const lower = host.toLowerCase();
  if (LOOPBACK_NAMES.has(lower)) return true;

  // Strip an optional zone id from IPv6 (e.g. "::1%lo0").
  const ipv6 = lower.replace(/%.*$/, "");
  if (ipv6 === "::1") return true;
  // Bracketed IPv6 from URL contexts: "[::1]"
  if (ipv6 === "[::1]") return true;

  // IPv4 — anything in 127.0.0.0/8.
  // Cheap, allocation-free check.
  if (/^127\.(?:\d{1,3})\.(?:\d{1,3})\.(?:\d{1,3})$/.test(host)) {
    const parts = host.split(".").map((n) => Number.parseInt(n, 10));
    if (parts.every((n) => Number.isInteger(n) && n >= 0 && n <= 255)) {
      return true;
    }
  }
  return false;
}

export function assertLoopbackHost(host: string, label = "host"): void {
  if (!isLoopbackHost(host)) {
    throw new Error(
      `DECEPTICON_WEB_AUTH=disable-bind-public refuses to bind ${label}=${host || "(all interfaces)"}.\n` +
        `Set ${label} to one of: 127.0.0.1, ::1, localhost. Aborting startup.`,
    );
  }
}
