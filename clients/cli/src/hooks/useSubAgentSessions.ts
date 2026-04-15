import { useMemo } from "react";
import type { AgentEvent, SubAgentSession } from "../types.js";
import { deriveSubAgentSessions } from "@decepticon/streaming";

/**
 * Derive structured sub-agent sessions from the flat event stream.
 *
 * Delegates to the shared deriveSubAgentSessions() function from
 * @decepticon/streaming, wrapped in useMemo for React performance.
 */
export function useSubAgentSessions(events: AgentEvent[]): SubAgentSession[] {
  return useMemo(() => deriveSubAgentSessions(events), [events]);
}
