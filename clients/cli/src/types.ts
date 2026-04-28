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
  | "subagent_end"
  | "ask_user_question"
  | "ask_user_answer";

/** One choice in an ask_user_question picker. */
export interface AskUserOption {
  label: string;
  description: string;
}

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
  // ask_user_question payload (for type === "ask_user_question").
  // `sourceId` is the deduplication key from the backend tool_call_id.
  sourceId?: string;
  question?: string;
  header?: string;
  options?: AskUserOption[];
  multiSelect?: boolean;
  allowOther?: boolean;
}

/** A pending operator question — present while a picker is awaiting input. */
export interface ActiveQuestion {
  /** tool_call_id from the backend; deduplicates re-emissions on resume. */
  sourceId: string;
  question: string;
  header: string;
  options: AskUserOption[];
  multiSelect: boolean;
  allowOther: boolean;
}

// SubAgentSession is exported from @decepticon/streaming
export type { SubAgentSession } from "@decepticon/streaming";
