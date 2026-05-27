/**
 * ConnectionStatus — inline notice rendered by REPL when the LangGraph stream
 * has dropped and useAgent's reconnect loop is working through its backoff
 * schedule. Renders nothing when the stream is healthy so it never steals
 * vertical space from the normal flow.
 *
 * States surfaced (from useAgent's ConnectionState):
 *   - status "connected" + justRecovered=false → renders nothing.
 *   - status "connected" + justRecovered=true  → green "Reconnected." flash
 *     that auto-dismisses after ~2s (the timer lives in useAgent).
 *   - status "reconnecting"                     → yellow line with attempt
 *     count and a live countdown to the next retry.
 *   - status "disconnected"                     → red line; operator should
 *     /resume to try again.
 *
 * The countdown re-renders once per second via a local interval; that's
 * cheap (only when the notice is visible) and avoids forcing useAgent to
 * re-render constantly during a long backoff.
 */

import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import type { ConnectionState } from "../hooks/useAgent.js";
import { GLYPH_DOT } from "../utils/theme.js";

interface ConnectionStatusProps {
  state: ConnectionState;
}

export const ConnectionStatus = React.memo(function ConnectionStatus({
  state,
}: ConnectionStatusProps) {
  // Local "now" tick so the countdown animates. Only ticks while a retry
  // is pending — switches off as soon as we land on "connected".
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (state.status !== "reconnecting") return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [state.status]);

  if (state.status === "connected") {
    if (!state.justRecovered) return null;
    return (
      <Box marginTop={1} height={1}>
        <Text color="green">
          {GLYPH_DOT} Reconnected.
        </Text>
      </Box>
    );
  }

  if (state.status === "reconnecting") {
    const remainingMs = Math.max(0, state.nextRetryAt - now);
    const remainingSec = Math.max(1, Math.ceil(remainingMs / 1000));
    return (
      <Box marginTop={1} height={1}>
        <Text color="yellow">
          {GLYPH_DOT} Reconnecting (attempt {state.attempt}, next try in{" "}
          {remainingSec}s)…
        </Text>
      </Box>
    );
  }

  // "disconnected"
  return (
    <Box marginTop={1} height={1}>
      <Text color="red">
        {GLYPH_DOT} Disconnected from server — type /resume to try again.
      </Text>
    </Box>
  );
});
