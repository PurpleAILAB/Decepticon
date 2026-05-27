import { describe, it, expect } from "vitest";
import { isLoopbackHost, assertLoopbackHost } from "./bind-public";

describe("isLoopbackHost", () => {
  it("accepts the canonical loopback names / addresses", () => {
    expect(isLoopbackHost("127.0.0.1")).toBe(true);
    expect(isLoopbackHost("localhost")).toBe(true);
    expect(isLoopbackHost("::1")).toBe(true);
    expect(isLoopbackHost("[::1]")).toBe(true);
    expect(isLoopbackHost("::1%lo0")).toBe(true);
  });

  it("accepts the rest of 127.0.0.0/8", () => {
    expect(isLoopbackHost("127.0.0.2")).toBe(true);
    expect(isLoopbackHost("127.1.2.3")).toBe(true);
    expect(isLoopbackHost("127.255.255.254")).toBe(true);
  });

  it("rejects 0.0.0.0 (all interfaces)", () => {
    expect(isLoopbackHost("0.0.0.0")).toBe(false);
  });

  it("rejects the empty string (which would mean all-interfaces in node's listen)", () => {
    expect(isLoopbackHost("")).toBe(false);
  });

  it("rejects IPv6 all-interfaces", () => {
    expect(isLoopbackHost("::")).toBe(false);
    expect(isLoopbackHost("[::]")).toBe(false);
  });

  it("rejects concrete LAN / public addresses", () => {
    expect(isLoopbackHost("10.0.0.1")).toBe(false);
    expect(isLoopbackHost("192.168.1.1")).toBe(false);
    expect(isLoopbackHost("8.8.8.8")).toBe(false);
    expect(isLoopbackHost("example.com")).toBe(false);
  });

  it("rejects strings that look like 127.* but aren't valid IPs", () => {
    expect(isLoopbackHost("127.999.0.1")).toBe(false);
    expect(isLoopbackHost("127.x.y.z")).toBe(false);
  });
});

describe("assertLoopbackHost", () => {
  it("returns silently for loopback hosts", () => {
    expect(() => assertLoopbackHost("127.0.0.1")).not.toThrow();
    expect(() => assertLoopbackHost("localhost")).not.toThrow();
    expect(() => assertLoopbackHost("::1")).not.toThrow();
  });

  it("throws with an explicit error for 0.0.0.0", () => {
    expect(() => assertLoopbackHost("0.0.0.0", "HOST")).toThrow(/disable-bind-public/);
    expect(() => assertLoopbackHost("0.0.0.0", "HOST")).toThrow(/HOST=0\.0\.0\.0/);
  });

  it("throws for an empty host (would otherwise bind all interfaces)", () => {
    expect(() => assertLoopbackHost("", "HOST")).toThrow(/all interfaces/);
  });

  it("includes the label in the error so the operator knows which knob to fix", () => {
    expect(() => assertLoopbackHost("0.0.0.0", "TERMINAL_HOST")).toThrow(/TERMINAL_HOST/);
  });
});

/**
 * Re-implements the host-resolution logic the terminal-server runs at
 * startup, so we can verify "kind: disable-bind-public + HOST=0.0.0.0
 * aborts with an explicit error" without spawning a subprocess.
 *
 * Mirrors `clients/web/server/terminal-server.ts`. If you change that
 * file's host-resolution block, update this helper too — or the
 * regression coverage will silently drift.
 */
function resolveTerminalListenHost(args: {
  authKind: "none" | "password" | "disable-bind-public";
  terminalHost: string;
}): string | undefined {
  if (args.authKind === "disable-bind-public") {
    if (args.terminalHost && !isLoopbackHost(args.terminalHost)) {
      assertLoopbackHost(args.terminalHost, "TERMINAL_HOST"); // throws
    }
    return args.terminalHost || "127.0.0.1";
  }
  return args.terminalHost || undefined;
}

describe("terminal-server startup — disable-bind-public guard (integration shape)", () => {
  it("HOST=127.0.0.1 starts cleanly (returns 127.0.0.1)", () => {
    expect(
      resolveTerminalListenHost({ authKind: "disable-bind-public", terminalHost: "127.0.0.1" }),
    ).toBe("127.0.0.1");
  });

  it("HOST unset starts cleanly with the default 127.0.0.1", () => {
    expect(
      resolveTerminalListenHost({ authKind: "disable-bind-public", terminalHost: "" }),
    ).toBe("127.0.0.1");
  });

  it("HOST=localhost starts cleanly", () => {
    expect(
      resolveTerminalListenHost({ authKind: "disable-bind-public", terminalHost: "localhost" }),
    ).toBe("localhost");
  });

  it("HOST=0.0.0.0 aborts with an explicit error", () => {
    expect(() =>
      resolveTerminalListenHost({ authKind: "disable-bind-public", terminalHost: "0.0.0.0" }),
    ).toThrow(/disable-bind-public/);
  });

  it("HOST=10.0.0.5 (LAN) aborts", () => {
    expect(() =>
      resolveTerminalListenHost({ authKind: "disable-bind-public", terminalHost: "10.0.0.5" }),
    ).toThrow(/disable-bind-public/);
  });

  it("does NOT touch the host in mode=none (regression guard — default behavior unchanged)", () => {
    expect(resolveTerminalListenHost({ authKind: "none", terminalHost: "" })).toBeUndefined();
    expect(resolveTerminalListenHost({ authKind: "none", terminalHost: "0.0.0.0" })).toBe("0.0.0.0");
  });
});
