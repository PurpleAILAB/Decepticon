import { describe, expect, it } from "vitest";
import { scanTierC } from "../src/tierc";

/**
 * The whole point of the gateway is that NONE of these ever reach PostHog. This
 * corpus is the §9.1 "regex corpus of IPs/creds/hosts → asserts no leak" gate.
 * Each must be caught even when buried inside a nested event field.
 */
const FORBIDDEN: ReadonlyArray<readonly [string, unknown]> = [
  ["ipv4", { tool: "nmap", target: "10.0.0.5" }],
  ["ipv4", "scan 192.168.1.1 please"],
  ["ipv6", "fe80::1ff:fe23:4567:890a"],
  ["domain", "target.example.com"],
  ["url", "exfil to https://evil.example/x"],
  ["email", "admin@corp.internal"],
  ["mac", "00:1b:44:11:3a:b7"],
  ["aws_access_key", "AKIAIOSFODNN7EXAMPLE"],
  ["jwt", "eyJhbGciOi.eyJzdWIiOiI.SflKxwRJSMeKKF2QT4"],
  ["private_key", "-----BEGIN RSA PRIVATE KEY-----"],
  ["user_pass", "admin:hunter2@db"],
  ["opaque_blob", "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYabcd1234"],
];

describe("scanTierC — forbidden content is always caught", () => {
  for (const [klass, payload] of FORBIDDEN) {
    it(`rejects ${klass}: ${JSON.stringify(payload).slice(0, 40)}`, () => {
      const hit = scanTierC(payload);
      expect(hit).not.toBeNull();
    });
  }

  it("catches a secret buried deep in an array of events", () => {
    const events = [
      { type: "tool.call", ts: 1 },
      { type: "tool.result", ts: 2, nested: ["clean", { deep: "10.20.30.40" }] },
    ];
    const hit = scanTierC(events);
    expect(hit?.klass).toBe("ipv4");
    // Path is structural only — no value echoed.
    expect(hit?.path).toContain("[1]");
    expect(JSON.stringify(hit)).not.toContain("10.20.30.40");
  });
});

describe("scanTierC — clean Tier-A content passes", () => {
  const CLEAN: unknown[] = [
    { type: "tool.call", ts: 1718880000, tool: "nmap", status: "ok" },
    { type: "finding.created", ts: 1, cwe: ["CWE-89"], cve: ["CVE-2021-44228"] },
    { type: "agent.turn", ts: 1, agent: "recon", mitre_techniques: ["T1046"] },
    { type: "llm.response", ts: 1, tokens: 1234, cost_usd: 0.0012 },
    { decepticon_version: "1.1.13", os: "linux", arch: "x86_64", py: "3.13" },
  ];
  for (const c of CLEAN) {
    it(`passes ${JSON.stringify(c).slice(0, 50)}`, () => {
      expect(scanTierC(c)).toBeNull();
    });
  }
});
