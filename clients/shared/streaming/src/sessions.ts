/**
 * Sub-agent session derivation — pure function, no React dependency.
 *
 * Groups a flat event stream into structured sessions by scanning for
 * subagent_start/subagent_end boundaries. Extracted from CLI's
 * useSubAgentSessions hook for cross-platform reuse.
 */

import type { StreamEvent } from "./types";

/** A sub-agent execution session derived from the event stream. */
export interface SubAgentSession {
  /** Unique session ID (from the subagent_start event). */
  id: string;
  /** Agent name (e.g. "recon", "exploit"). */
  agent: string;
  /** Human-readable description of the task. */
  description: string;
  /** ID of the subagent_start event. */
  startEventId: string;
  /** ID of the subagent_end event (undefined if still running). */
  endEventId?: string;
  /** All event IDs belonging to this session. */
  eventIds: string[];
  /** Number of tool_result + bash_result events in the session. */
  toolCount: number;
  /** Session start timestamp. */
  startTime: number;
  /** Session end timestamp (undefined if still running). */
  endTime?: number;
  /** Current session status. */
  status: "running" | "completed" | "error";
}

/**
 * Derive structured sub-agent sessions from a flat event stream.
 *
 * Sessions are built by scanning for subagent_start/subagent_end events
 * and collecting all events with a matching `subagent` field between them.
 *
 * @param events - Flat array of events with at minimum: id, type, subagent?, content?, timestamp
 * @returns Array of derived sessions in chronological order
 */
export function deriveSubAgentSessions(events: readonly StreamEvent[]): SubAgentSession[] {
  const sessions: SubAgentSession[] = [];
  const openSessions = new Map<string, SubAgentSession>();

  for (const event of events) {
    if (event.type === "subagent_start" && event.subagent) {
      const session: SubAgentSession = {
        id: event.id,
        agent: event.subagent,
        description: event.content || `Starting ${event.subagent}`,
        startEventId: event.id,
        eventIds: [event.id],
        toolCount: 0,
        startTime: event.timestamp,
        status: "running",
      };
      openSessions.set(event.subagent, session);
      sessions.push(session);
    } else if (event.type === "subagent_end" && event.subagent) {
      const session = openSessions.get(event.subagent);
      if (session) {
        session.endEventId = event.id;
        session.endTime = event.timestamp;
        session.status = event.type === "subagent_end" && (event as { status?: string }).status === "error"
          ? "error"
          : "completed";
        session.eventIds.push(event.id);
        openSessions.delete(event.subagent);
      }
    } else if (event.subagent) {
      const session = openSessions.get(event.subagent);
      if (session) {
        session.eventIds.push(event.id);
        if (event.type === "tool_result" || event.type === "bash_result") {
          session.toolCount++;
        }
      }
    }
  }

  return sessions;
}
