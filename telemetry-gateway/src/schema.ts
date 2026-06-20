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
  // Research tier: an identifier-masked reasoning/trajectory step.
  "trajectory.step",
] as const;

/** Masked free text (reasoning/prompt/observation). Bounded; re-scanned for Tier-C. */
const MaskedText = z.string().max(16000);

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
    /** Normalized tool result status. Client maps "success"->"ok"; "command" is dropped. */
    status: z.enum(["ok", "error"]).optional(),
    /** Model id, e.g. "claude-opus-4-8" — provider/model mix, non-identifying. */
    model: Slug.optional(),
    /** Coarse request/finding classification enum (Tier B), never free text. */
    category: Slug.optional(),
    attack_phase: Slug.optional(),
    duration_ms: z.number().finite().nonnegative().optional(),
    tokens: z.number().int().nonnegative().optional(),
    cost_usd: z.number().finite().nonnegative().optional(),
    count: z.number().int().nonnegative().optional(),
    /** Bucketed tool-output size (e.g. "1k-10k") — never the exact byte count. */
    output_bucket: z.enum(["0-128", "128-1k", "1k-10k", "10k+"]).optional(),
    /** Bucketed LLM-call message count (e.g. "10-50"). */
    msgs_bucket: z.enum(["1-5", "5-10", "10-50", "50+"]).optional(),
    /** Bucketed prompt length (e.g. "50-100") — never the prompt itself. */
    prompt_len_bucket: Slug.optional(),
    // ── ground-truth engagement classification (from the Finding model / OPPLAN) ──
    /** Finding severity: critical/high/medium/low/informational. */
    severity: Slug.optional(),
    /** Finding confidence: verified/probable/unverified. */
    confidence: Slug.optional(),
    /** Purple-team detection flag: yes / no. */
    detected: Slug.optional(),
    /** Kill-chain phase: recon/initial-access/post-exploit/c2/exfiltration. */
    phase: Slug.optional(),
    /** OPPLAN objective status: pending/in-progress/completed/blocked/cancelled. */
    status_objective: Slug.optional(),
    // ── research trajectory step (all masked client-side, re-verified here) ──
    /** model = a reasoning turn; tool = an action+observation. */
    kind: z.enum(["model", "tool"]).optional(),
    /** Monotonic step index within a session. */
    step: z.number().int().nonnegative().optional(),
    /** Session correlation id (random, not machine-derived). */
    session_id: z.string().max(64).optional(),
    /** Masked input/objective context for this step. */
    prompt: MaskedText.optional(),
    /** Masked agent chain-of-thought / tactic rationale — the corpus payload. */
    reasoning: MaskedText.optional(),
    /** Masked tool output / observation. */
    observation: MaskedText.optional(),
    /** Masked tool arguments (the actual command), free-form. */
    args_text: MaskedText.optional(),
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
    tier: z.enum(["A", "R"]),
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
