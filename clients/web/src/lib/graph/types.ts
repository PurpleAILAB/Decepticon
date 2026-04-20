/**
 * Agent execution graph types for the force-directed visualization.
 *
 * Graph topology mirrors octogent's hierarchy:
 *
 *   ORCHESTRATOR (Decepticon, center hub)
 *   ├── AGENT (kill-chain workers, arranged in circle)
 *   │   ├── TOOL-SESSION (active tool call, small satellite node)
 *   │   └── COMPLETED-SESSION (finished tool, dimmed satellite)
 *   └── ...
 *
 * Runtime states:
 * - idle: not doing anything
 * - processing: actively working on a task
 * - waiting_for_permission: needs tool-use approval
 * - waiting_for_user: needs user text input
 * - completed: finished execution
 */

export type AgentRuntimeState =
  | "idle"
  | "processing"
  | "waiting_for_permission"
  | "waiting_for_user"
  | "completed"
  | "failed";

export type GraphNodeType = "orchestrator" | "agent" | "tool-session" | "completed-session";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  x: number;
  y: number;
  vx: number;
  vy: number;
  pinned: boolean;
  radius: number;
  agentId: string;
  label: string;
  color: string;
  runtimeState: AgentRuntimeState;
  mascotEmoji: string;
  role: string;
  /** Tool name when in waiting_for_permission state or for tool-session nodes. */
  waitingToolName?: string;
  /** Parent agent ID for session nodes. */
  parentAgentId?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  active: boolean;
}

export function isWaitingState(s: AgentRuntimeState): boolean {
  return s === "waiting_for_permission" || s === "waiting_for_user";
}
