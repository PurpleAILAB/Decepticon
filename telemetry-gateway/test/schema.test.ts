import { describe, expect, it } from "vitest";
import { TelemetryBatch } from "../src/schema";

const VALID = {
  schema_version: "1.0",
  tier: "A",
  install_id: "1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
  engagement_hash: "a1b2c3d4e5f60718",
  client: { decepticon_version: "1.1.13", os: "linux", arch: "x86_64", py: "3.13" },
  events: [
    { type: "tool.call", ts: 1718880000, tool: "nmap", status: "ok", duration_ms: 1200 },
    { type: "agent.turn", ts: 1718880001, agent: "recon", mitre_techniques: ["T1046"] },
    { type: "finding.created", ts: 1718880002, category: "sqli", cwe: ["CWE-89"] },
  ],
} as const;

describe("TelemetryBatch schema", () => {
  it("accepts a well-formed Tier-A batch", () => {
    expect(TelemetryBatch.safeParse(VALID).success).toBe(true);
  });

  it("rejects an unknown top-level key (strict envelope)", () => {
    const bad = { ...VALID, raw_prompt: "list shares on 10.0.0.5" };
    expect(TelemetryBatch.safeParse(bad).success).toBe(false);
  });

  it("rejects an unknown event field (strict event)", () => {
    const bad = { ...VALID, events: [{ type: "tool.call", ts: 1, command: "nmap -sV 10.0.0.5" }] };
    expect(TelemetryBatch.safeParse(bad).success).toBe(false);
  });

  it("rejects a non-UUID install_id", () => {
    expect(TelemetryBatch.safeParse({ ...VALID, install_id: "device-42" }).success).toBe(false);
  });

  it("rejects a malformed MITRE technique", () => {
    const bad = { ...VALID, events: [{ type: "agent.turn", ts: 1, mitre_techniques: ["nmap-scan"] }] };
    expect(TelemetryBatch.safeParse(bad).success).toBe(false);
  });

  it("rejects an empty events array", () => {
    expect(TelemetryBatch.safeParse({ ...VALID, events: [] }).success).toBe(false);
  });
});
