/**
 * @decepticon/streaming — Shared LangGraph streaming infrastructure.
 *
 * Provides the canonical event types, stream configuration, and utility
 * functions used by both the Web dashboard and CLI clients.
 *
 * Source-only package — consumers transpile this directly via Next.js
 * `transpilePackages` or tsx. No build step.
 */

// Types
export type { SubagentCustomEvent, SubagentEventType, StreamEvent } from "./types";

// Constants
export { STREAM_OPTIONS } from "./constants";

// Utilities
export { extractText, stripResultTags } from "./utils";

// Session derivation
export type { SubAgentSession } from "./sessions";
export { deriveSubAgentSessions } from "./sessions";
