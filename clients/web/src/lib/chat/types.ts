/**
 * Chat types for the web dashboard.
 *
 * MessageRenderer handles output display — swappable for OpenUI (GenUI) in the future.
 */

// ── Message types ────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "tool" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  agent?: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  timestamp: number;
  documents?: DocumentRef[];
  status?: "passed" | "blocked";
}

export interface DocumentRef {
  id: string;
  title: string;
  type: "roe" | "conops" | "opplan" | "finding" | "reference";
}

// ── Renderer interface ───────────────────────────────────────────

/**
 * Abstract message renderer — decides how assistant content is displayed.
 *
 * MarkdownRenderer: renders content as rich markdown (react-markdown)
 * OpenUIRenderer:   renders content as GenUI components (future)
 */
export interface MessageRenderer {
  renderAssistantContent(content: string): React.ReactNode;
  renderToolOutput(content: string): React.ReactNode;
}
