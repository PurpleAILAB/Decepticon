import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  AuthError,
  requireAuth,
  isAuthEnabled,
  __resetAuthModeCacheForTests,
} from "./auth-bridge";
import { hashPassword } from "./auth-mode";

const PLAINTEXT = "hunter2";
const HASH = hashPassword(PLAINTEXT, { N: 1024 }); // cheap N for tests

function basicAuth(user: string, pass: string): string {
  return "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
}

describe("requireAuth — default (no auth)", () => {
  beforeEach(() => {
    delete process.env.DECEPTICON_WEB_AUTH;
    __resetAuthModeCacheForTests();
  });

  afterEach(() => {
    __resetAuthModeCacheForTests();
  });

  it("returns the local user when DECEPTICON_WEB_AUTH is unset (regression guard for default behavior)", async () => {
    const result = await requireAuth();
    expect(result).toEqual({ userId: "local", session: null });
  });

  it("isAuthEnabled() is false in default mode", () => {
    expect(isAuthEnabled()).toBe(false);
  });

  it("returns the local user when DECEPTICON_WEB_AUTH=none", async () => {
    process.env.DECEPTICON_WEB_AUTH = "none";
    __resetAuthModeCacheForTests();
    const result = await requireAuth();
    expect(result).toEqual({ userId: "local", session: null });
  });

  it("returns the local user even with garbage in the Authorization header (default mode)", async () => {
    const req = new Request("http://localhost/", {
      headers: { authorization: "Bearer total-garbage" },
    });
    const result = await requireAuth(req);
    expect(result).toEqual({ userId: "local", session: null });
  });
});

describe("requireAuth — password mode", () => {
  beforeEach(() => {
    process.env.DECEPTICON_WEB_AUTH = `password:${HASH}`;
    __resetAuthModeCacheForTests();
  });

  afterEach(() => {
    delete process.env.DECEPTICON_WEB_AUTH;
    __resetAuthModeCacheForTests();
  });

  it("isAuthEnabled() is true", () => {
    expect(isAuthEnabled()).toBe(true);
  });

  it("rejects requests with no Authorization header", async () => {
    const req = new Request("http://localhost/");
    await expect(requireAuth(req)).rejects.toBeInstanceOf(AuthError);
  });

  it("rejects requests with a malformed Authorization header", async () => {
    const req = new Request("http://localhost/", {
      headers: { authorization: "Basic !!!not-base64!!!" },
    });
    await expect(requireAuth(req)).rejects.toBeInstanceOf(AuthError);
  });

  it("accepts requests with the correct credentials", async () => {
    const req = new Request("http://localhost/", {
      headers: { authorization: basicAuth("admin", PLAINTEXT) },
    });
    const result = await requireAuth(req);
    expect(result).toEqual({ userId: "local", session: null });
  });

  it("rejects requests with the wrong password", async () => {
    const req = new Request("http://localhost/", {
      headers: { authorization: basicAuth("admin", "wrongpassword") },
    });
    await expect(requireAuth(req)).rejects.toBeInstanceOf(AuthError);
  });

  it("accepts a plain Headers object too", async () => {
    const h = new Headers({ authorization: basicAuth("any", PLAINTEXT) });
    const result = await requireAuth(h);
    expect(result).toEqual({ userId: "local", session: null });
  });
});

describe("requireAuth — disable-bind-public mode", () => {
  beforeEach(() => {
    process.env.DECEPTICON_WEB_AUTH = "disable-bind-public";
    __resetAuthModeCacheForTests();
  });

  afterEach(() => {
    delete process.env.DECEPTICON_WEB_AUTH;
    __resetAuthModeCacheForTests();
  });

  it("auth layer behaves like 'none' — bind restriction is enforced elsewhere", async () => {
    const result = await requireAuth();
    expect(result).toEqual({ userId: "local", session: null });
  });

  it("isAuthEnabled() is false (no per-request auth)", () => {
    expect(isAuthEnabled()).toBe(false);
  });
});

describe("requireAuth — malformed env aborts at first call (fail loud)", () => {
  beforeEach(() => {
    process.env.DECEPTICON_WEB_AUTH = "garbage-value";
    __resetAuthModeCacheForTests();
  });

  afterEach(() => {
    delete process.env.DECEPTICON_WEB_AUTH;
    __resetAuthModeCacheForTests();
  });

  it("throws synchronously rather than silently degrading to 'none'", async () => {
    // Note: the parse error is thrown from inside requireAuth when it first
    // resolves the mode. We want to verify we don't quietly return success.
    await expect(requireAuth()).rejects.toThrow(/DECEPTICON_WEB_AUTH/);
  });
});
