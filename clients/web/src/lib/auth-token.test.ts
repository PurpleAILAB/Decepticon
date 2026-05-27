import { describe, it, expect } from "vitest";
import { deriveWsToken, tokensEqual, extractWsToken } from "./auth-token";

describe("deriveWsToken", () => {
  it("is deterministic for a given hash", () => {
    const hash = "scrypt$1024$8$1$YWFh$YmJi";
    expect(deriveWsToken(hash)).toBe(deriveWsToken(hash));
  });

  it("produces 64 lowercase hex chars (SHA-256)", () => {
    const t = deriveWsToken("scrypt$1024$8$1$YWFh$YmJi");
    expect(t).toMatch(/^[0-9a-f]{64}$/);
  });

  it("differs for different hashes", () => {
    const a = deriveWsToken("scrypt$1024$8$1$YWFh$YmJi");
    const b = deriveWsToken("scrypt$1024$8$1$Y2Nj$ZGRk");
    expect(a).not.toBe(b);
  });
});

describe("tokensEqual", () => {
  it("returns true for equal hex strings", () => {
    expect(tokensEqual("abcd1234", "abcd1234")).toBe(true);
  });

  it("returns false for different strings of the same length", () => {
    expect(tokensEqual("abcd1234", "abcd1235")).toBe(false);
  });

  it("returns false for different lengths (avoid length-leak via timingSafeEqual)", () => {
    expect(tokensEqual("abcd", "abcd1234")).toBe(false);
  });

  it("returns false for non-string inputs", () => {
    // @ts-expect-error — runtime defensive path
    expect(tokensEqual(undefined, "abcd")).toBe(false);
    // @ts-expect-error
    expect(tokensEqual("abcd", null)).toBe(false);
  });
});

describe("extractWsToken", () => {
  it("reads from `Authorization: Bearer <hex>`", () => {
    const url = new URL("ws://localhost:3003/");
    expect(extractWsToken("Bearer deadbeef", url)).toBe("deadbeef");
  });

  it("normalizes uppercase hex to lowercase", () => {
    const url = new URL("ws://localhost:3003/");
    expect(extractWsToken("Bearer DEADBEEF", url)).toBe("deadbeef");
  });

  it("reads from ?token= when no header is present", () => {
    const url = new URL("ws://localhost:3003/?token=deadbeef");
    expect(extractWsToken(undefined, url)).toBe("deadbeef");
  });

  it("rejects non-hex Bearer payloads", () => {
    const url = new URL("ws://localhost:3003/");
    expect(extractWsToken("Bearer not-hex!", url)).toBeNull();
  });

  it("rejects non-hex query params", () => {
    const url = new URL("ws://localhost:3003/?token=not-hex!");
    expect(extractWsToken(undefined, url)).toBeNull();
  });

  it("prefers the Authorization header over the query string", () => {
    const url = new URL("ws://localhost:3003/?token=ffff");
    expect(extractWsToken("Bearer aaaa", url)).toBe("aaaa");
  });

  it("returns null when neither source has a token", () => {
    const url = new URL("ws://localhost:3003/");
    expect(extractWsToken(undefined, url)).toBeNull();
  });
});
