/**
 * @decepticon/streaming — Shared LangGraph streaming infrastructure.
 *
 * Provides the canonical event types, stream configuration, and utility
 * functions used by both the Web dashboard and CLI clients.
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
