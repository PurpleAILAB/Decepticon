import { describe, expect, it } from "vitest";
import { TelemetryBatch } from "../src/schema";

const VALID = {
  schema_version: "1.0",
  tier: "A",
  install_id: "1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
  client: { decepticon_version: "1.1.13", os: "linux", arch: "x86_64", py: "3.13" },
  events: [
    { type: "tool.call", ts: 1718880000, tool: "nmap", status: "ok", duration_ms: 1200 },
    { type: "agent.turn", ts: 1718880001, agent: "recon", mitre_techniques: ["T1046"] },
    { type: "finding.created", ts: 1718880002, category: "sqli", cwe: ["CWE-89"] },
    { type: "llm.call", ts: 1718880003, model: "claude-opus-4-8", msgs_bucket: "10-50" },
    { type: "tool.result", ts: 1718880004, tool: "bash", status: "ok", output_bucket: "1k-10k" },
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

  it("rejects an out-of-enum output_bucket", () => {
    const bad = { ...VALID, events: [{ type: "tool.result", ts: 1, output_bucket: "huge" }] };
    expect(TelemetryBatch.safeParse(bad).success).toBe(false);
  });

  it("accepts ground-truth finding / opplan events", () => {
    const batch = {
      ...VALID,
      events: [
        { type: "finding.created", ts: 1, agent: "exploit", severity: "high", confidence: "verified", detected: "no", phase: "initial-access", cwe: ["CWE-89"], mitre_techniques: ["T1190"] },
        { type: "opplan.update", ts: 2, phase: "recon", status_objective: "pending" },
      ],
    };
    expect(TelemetryBatch.safeParse(batch).success).toBe(true);
  });

  it("rejects a removed event type (hitl.decision / user.input)", () => {
    const bad = { ...VALID, events: [{ type: "hitl.decision", ts: 1, decision: "deny" }] };
    expect(TelemetryBatch.safeParse(bad).success).toBe(false);
  });

  it("accepts a masked research trajectory step", () => {
    const batch = {
      ...VALID,
      tier: "R",
      events: [
        {
          type: "trajectory.step",
          ts: 1,
          role: "agent",
          step: 7,
          agent: "exploit",
          session_id: "s-abc",
          text: "The login at <DOMAIN_1> on <HOST_1> looks injectable; try UNION-based SQLi.",
          args_text: "sqlmap -u <URL_1> --batch",
        },
      ],
    };
    expect(TelemetryBatch.safeParse(batch).success).toBe(true);
  });

  it("caps masked text length", () => {
    const bad = { ...VALID, events: [{ type: "trajectory.step", ts: 1, text: "x".repeat(16001) }] };
    expect(TelemetryBatch.safeParse(bad).success).toBe(false);
  });
});
