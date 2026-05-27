import { describe, it, expect } from "vitest";
import { parseAuthMode, parseScryptHash, hashPassword, verifyPassword } from "./auth-mode";

describe("parseAuthMode", () => {
  it("defaults to {kind:'none'} when env is undefined", () => {
    expect(parseAuthMode(undefined)).toEqual({ kind: "none" });
  });

  it("treats empty / whitespace as none (preserves default behavior)", () => {
    expect(parseAuthMode("")).toEqual({ kind: "none" });
    expect(parseAuthMode("   ")).toEqual({ kind: "none" });
  });

  it("parses 'none' explicitly", () => {
    expect(parseAuthMode("none")).toEqual({ kind: "none" });
  });

  it("parses 'disable-bind-public'", () => {
    expect(parseAuthMode("disable-bind-public")).toEqual({ kind: "disable-bind-public" });
  });

  it("parses 'password:<scrypt-hash>'", () => {
    const hash = hashPassword("hunter2", { N: 1024 });
    const result = parseAuthMode(`password:${hash}`);
    expect(result.kind).toBe("password");
    if (result.kind === "password") {
      expect(result.hash.raw).toBe(hash);
      expect(result.hash.N).toBe(1024);
    }
  });

  it("throws on garbage", () => {
    expect(() => parseAuthMode("garbage")).toThrow(/DECEPTICON_WEB_AUTH/);
  });

  it("throws on 'password:' with a non-scrypt payload", () => {
    expect(() => parseAuthMode("password:notavalidhash")).toThrow(/scrypt/i);
  });

  it("throws on 'password:' with a bcrypt-looking payload (we only support scrypt)", () => {
    expect(() => parseAuthMode("password:$2b$12$abcdefghijklmnop")).toThrow(/scrypt/i);
  });

  it("throws on a malformed scrypt hash (wrong number of fields)", () => {
    expect(() => parseAuthMode("password:scrypt$1024$8$1$onlyfivefields")).toThrow(
      /6 .*-separated fields/,
    );
  });

  it("throws on a non-power-of-two N", () => {
    expect(() => parseScryptHash("scrypt$1023$8$1$YWFh$YmJi")).toThrow(/power of two/);
  });
});

describe("hashPassword / verifyPassword", () => {
  it("verifies the correct plaintext", () => {
    const hash = hashPassword("correct horse battery staple", { N: 1024 });
    const parsed = parseScryptHash(hash);
    expect(verifyPassword("correct horse battery staple", parsed)).toBe(true);
  });

  it("rejects a wrong plaintext", () => {
    const hash = hashPassword("hunter2", { N: 1024 });
    const parsed = parseScryptHash(hash);
    expect(verifyPassword("hunter3", parsed)).toBe(false);
  });

  it("produces unique hashes for the same plaintext (random salt)", () => {
    const a = hashPassword("p", { N: 1024 });
    const b = hashPassword("p", { N: 1024 });
    expect(a).not.toBe(b);
  });
});
