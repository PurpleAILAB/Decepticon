/**
 * Canonical Tier-A telemetry contract.
 *
 * This Zod schema is the *runtime* enforcement of the wire format the
 * Decepticon client emits to the gateway. The language-neutral mirror lives in
 * `schema.json` (JSON Schema) so the Python client can validate against the
 * same shape — the two MUST stay in sync (see README §Schema).
 *
 * Design rule (matches the design doc, decision §0): the envelope carries only
 * Tier A *structural* data — never raw prompts, targets, credentials, or tool
 * output. The schema is intentionally a closed allow-list of scalar/enum
 * fields: anything not named here is `.strip()`-ed away before forwarding, and
 * the Tier-C scanner (see `tierc.ts`) is the second, content-level safety net.
 */
import { z } from "zod";

/** Event types mirror `decepticon.runtime.event_log.EventType` (the dotted values). */
export const EVENT_TYPES = [
  "engagement.start",
  "engagement.end",
  "engagement.checkpoint",
  "agent.turn",
  "tool.call",
  "tool.result",
  "llm.call",
  "llm.response",
  "finding.created",
  "opplan.update",
] as const;

/** Short, low-cardinality identifiers only — no free text, no dots, no spaces. */
const Slug = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[a-z0-9][a-z0-9._-]*$/i, "must be a short slug (no spaces/free text)");

const MitreTechnique = z.string().regex(/^T\d{4}(\.\d{3})?$/);
const MitreTactic = z.string().regex(/^TA\d{4}$/);
const Cwe = z.string().regex(/^CWE-\d{1,5}$/);
const Cve = z.string().regex(/^CVE-\d{4}-\d{4,7}$/);

/**
 * One telemetry event. Every field is non-identifying and optional except
 * `type` and `ts`. `.strict()` rejects unknown keys outright so a future client
 * bug cannot smuggle a free-text field past the contract.
 */
export const TelemetryEvent = z
  .object({
    type: z.enum(EVENT_TYPES),
    ts: z.number().finite().nonnegative(),
    /** Emitting agent — one of the 16 specialist names, an enum-like slug. */
    agent: Slug.optional(),
    /** Tool name / command binary, e.g. "nmap", "sqlmap" — never the full command. */
    tool: Slug.optional(),
    status: z.enum(["ok", "error"]).optional(),
    /** Coarse request/finding classification enum (Tier B), never free text. */
    category: Slug.optional(),
    attack_phase: Slug.optional(),
    duration_ms: z.number().finite().nonnegative().optional(),
    tokens: z.number().int().nonnegative().optional(),
    cost_usd: z.number().finite().nonnegative().optional(),
    count: z.number().int().nonnegative().optional(),
    /** Bucketed prompt length (e.g. "50-100") — never the prompt itself. */
    prompt_len_bucket: Slug.optional(),
    mitre_tactics: z.array(MitreTactic).max(16).optional(),
    mitre_techniques: z.array(MitreTechnique).max(32).optional(),
    cwe: z.array(Cwe).max(16).optional(),
    cve: z.array(Cve).max(16).optional(),
  })
  .strict();

export type TelemetryEvent = z.infer<typeof TelemetryEvent>;

/** Non-identifying client/runtime descriptor. */
export const ClientInfo = z
  .object({
    decepticon_version: z
      .string()
      .max(32)
      .regex(/^[0-9A-Za-z.+_-]+$/),
    os: z.enum(["linux", "darwin", "windows"]),
    arch: Slug.optional(),
    py: z
      .string()
      .max(16)
      .regex(/^\d+\.\d+(\.\d+)?$/)
      .optional(),
  })
  .strict();

/**
 * The batch envelope. `install_id` is a random UUID minted on first run (never
 * machine/IP derived); `engagement_hash` is a non-reversible hash. Neither is
 * personally identifying.
 */
export const TelemetryBatch = z
  .object({
    schema_version: z.literal("1.0"),
    tier: z.enum(["A", "B"]),
    install_id: z.string().uuid(),
    engagement_hash: z
      .string()
      .regex(/^[a-f0-9]{16,64}$/)
      .optional(),
    client: ClientInfo,
    events: z.array(TelemetryEvent).min(1).max(500),
  })
  .strict();

export type TelemetryBatch = z.infer<typeof TelemetryBatch>;
