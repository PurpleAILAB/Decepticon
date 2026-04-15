/** Message roles in the conversation. */
export type Role = "user" | "assistant" | "tool";

/** A chat message displayed in the message list. */
export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
}

/** Tool call event from LangGraph streaming. */
export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

/** Tool result after execution. */
export interface ToolResult {
  toolCallId: string;
  name: string;
  content: string;
}

/** Custom event types emitted by Decepticon agents. */
export enum EventType {
  SubagentStart = "subagent_start",
  SubagentEnd = "subagent_end",
  Progress = "progress",
}

/** Screen display modes — prompt (compact) vs transcript (full). */
export type ScreenMode = "prompt" | "transcript";

/** Agent event types for CLI activity display. */
export type AgentEventType =
  | "user"
  | "tool_result"
  | "bash_result"
  | "ai_message"
  | "delegate"
  | "system"
  | "subagent_start"
  | "subagent_end";

/** A single displayable event in the agent activity stream. */
export interface AgentEvent {
  id: string;
  type: AgentEventType;
  content: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  status?: "success" | "error";
  /** Sub-agent name if event originated from a sub-agent. */
  subagent?: string;
  timestamp: number;
}

// SubAgentSession is exported from @decepticon/streaming
export type { SubAgentSession } from "@decepticon/streaming";
