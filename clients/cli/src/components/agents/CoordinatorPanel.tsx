/**
 * CoordinatorPanel — dynamic region sub-agent display.
 *
 * Shows currently running sub-agent sessions using Claude Code's inline
 * format via AgentSessionGroup.
 */

import React, { useMemo } from "react";
import { Box } from "ink";
import { AgentSessionGroup } from "./AgentSessionGroup.js";
import type { AgentEvent, SubAgentSession } from "../../types.js";

interface Props {
  sessions: SubAgentSession[];
  events: AgentEvent[];
}

export const CoordinatorPanel = React.memo(function CoordinatorPanel({
  sessions,
  events,
}: Props) {
  const visible = useMemo(
    () => sessions.filter((s) => s.status === "running"),
    [sessions],
  );

  if (visible.length === 0) return null;

  return (
    <Box flexDirection="column">
      {visible.map((session) => (
        <AgentSessionGroup
          key={session.id}
          session={session}
          events={events}
          screen="prompt"
        />
      ))}
    </Box>
  );
});
