/**
 * @decepticon/streaming — Shared LangGraph streaming infrastructure.
 *
 * Provides the canonical event types, stream configuration, and utility
 * functions used by both the Web dashboard and CLI clients.
 *
 * Built to ESM via tsc; relative specifiers carry the `.js` suffix so
 * Node's ESM resolver accepts the emitted dist/ at runtime (Next.js and
 * TS resolve the source via package `exports`).
 */

// Types
export type { SubagentCustomEvent, SubagentEventType, StreamEvent } from "./types.js";

// Constants
export { STREAM_OPTIONS } from "./constants.js";

// Utilities
export { extractText, stripResultTags } from "./utils.js";

// Session derivation
export type { SubAgentSession } from "./sessions.js";
export { deriveSubAgentSessions } from "./sessions.js";
