/**
 * Canonical event types from StreamingRunnable's get_stream_writer().
 *
 * This is the single source of truth — both Web and CLI import from here.
 * Matches the backend contract at decepticon/core/subagent_streaming.py.
 */

/** String literal union of all sub-agent event types. */
export type SubagentEventType =
  | "subagent_start"
  | "subagent_end"
  | "subagent_tool_call"
  | "subagent_tool_result"
  | "subagent_message";

/** Custom event payload from StreamingRunnable's get_stream_writer(). */
export interface SubagentCustomEvent {
  type: SubagentEventType;
  agent: string;
  tool?: string;
  args?: Record<string, unknown>;
  content?: string;
  text?: string;
  prompt?: string;
  elapsed?: number;
  status?: string;
  cancelled?: boolean;
  error?: boolean;
}

/** Minimal event shape accepted by shared utility functions. */
export interface StreamEvent {
  id: string;
  type: string;
  content?: string;
  subagent?: string;
  timestamp: number;
}
