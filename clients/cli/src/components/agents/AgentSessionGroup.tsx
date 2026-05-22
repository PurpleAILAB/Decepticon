/**
 * AgentSessionGroup — hybrid sub-agent display.
 *
 * Prompt mode (compact — Claude Code pattern):
 *   ● Recon(Scan target network for open ports)
 *     ⎿  Prompt:
 *          Execute comprehensive port scanning...
 *     ⎿  Bash(nmap -sV 192.168.1.0/24)
 *     ⎿  Read(recon/nmap.txt)
 *     ⎿  Response:
 *          Scan complete. Found 3 open ports...
 *     ⎿  Done (8 tool uses · 45s)
 *
 * Transcript mode (full — main agent style):
 *   ● Recon(Scan target network for open ports)
 *     ⎿  Prompt:
 *          Execute comprehensive port scanning...
 *     [full EventItem renders — bash output, AI messages, tool results]
 *     ⎿  Done (8 tool uses · 45s)
 *
 * Rationale: Decepticon sub-agents (recon, exploit, postexploit) execute
 * the actual attack — their bash output and AI reasoning are core content,
 * not auxiliary detail. Compact summaries lose critical information.
 */

import React, { useMemo, useState, useEffect } from "react";
import { Box, Text } from "ink";
import type { AgentEvent, ScreenMode, SubAgentSession } from "../../types.js";
import { GLYPH_DOT, GLYPH_HOOK, GLYPH_SEP, AGENT_COLORS } from "../../utils/theme.js";
import { compactToolLine, formatDuration } from "../../utils/format.js";
import { SubAgentProvider } from "../shell/SubAgentContext.js";
import { EventItem } from "../EventItem.js";

const MAX_PROMPT_LINES_COMPACT = 3;
const MAX_RESPONSE_LINES_COMPACT = 3;
const MAX_TOOL_LINES_COMPACT = 6;

interface Props {
  session: SubAgentSession;
  events: AgentEvent[];
  screen: ScreenMode;
  isLast?: boolean;
  pendingToolName?: string;
}

/** Capitalize first letter of agent name. */
function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Truncate text to N lines. */
function truncText(text: string, maxLines: number): { lines: string[]; truncated: boolean } {
  const all = text.split("\n");
  if (all.length <= maxLines) return { lines: all, truncated: false };
  return { lines: all.slice(0, maxLines), truncated: true };
}

// ── Shared header + prompt ───────────────────────────────────────

function SessionHeader({
  session,
  isRunning,
  color,
  maxPromptLines,
}: {
  session: SubAgentSession;
  isRunning: boolean;
  color: string;
  maxPromptLines: number;
}) {
  const dotColor = isRunning ? "gray" : session.status === "error" ? "red" : "green";
  const headerDesc = session.description.split("\n")[0] ?? session.description;
  const prompt = truncText(session.description, maxPromptLines);

  return (
    <>
      {/* Header: ● AgentType(short description) */}
      <Text>
        <Text color={dotColor}>{`${GLYPH_DOT} `}</Text>
        <Text bold color={color}>{capitalize(session.agent)}</Text>
        <Text dimColor italic>{`(${headerDesc})`}</Text>
      </Text>

      {/* Prompt section — hidden in prompt mode (shown via DelegateMessage instead) */}
      {maxPromptLines > 0 && (
        <>
          <Text dimColor>{`  ${GLYPH_HOOK}  Prompt:`}</Text>
          {prompt.lines.map((line, i) => (
            <Text key={`p${i}`} dimColor wrap="wrap">
              {`       ${line}`}
            </Text>
          ))}
          {prompt.truncated && (
            <Text dimColor italic>{"       ..."}</Text>
          )}
        </>
      )}
    </>
  );
}

// ── Shared footer (live-ticking elapsed time) ───────────────────

function SessionFooter({
  session,
}: {
  session: SubAgentSession;
}) {
  const isRunning = session.status === "running";
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  const elapsed = formatDuration((session.endTime ?? now) - session.startTime);
  const toolText = `${session.toolCount} tool use${session.toolCount !== 1 ? "s" : ""}`;
  const statsText = `${toolText}${GLYPH_SEP}${elapsed}`;

  return isRunning ? (
    <Text dimColor italic>{`  ${GLYPH_HOOK}  Running (${statsText})`}</Text>
  ) : (
    <Text dimColor>{`  ${GLYPH_HOOK}  Done (${statsText})`}</Text>
  );
}

// ── Main component ───────────────────────────────────────────────

export const AgentSessionGroup = React.memo(function AgentSessionGroup({
  session,
  events,
  screen,
}: Props) {
  const isTranscript = screen === "transcript";
  const isRunning = session.status === "running";
  const color = AGENT_COLORS[session.agent] ?? "white";

  // Filter events belonging to this session
  const sessionEvents = useMemo(() => {
    const idSet = new Set(session.eventIds);
    return events.filter((e) => idSet.has(e.id));
  }, [events, session.eventIds]);

  // ── Transcript mode: full EventItem rendering ──────────────────
  if (isTranscript) {
    const innerEvents = sessionEvents.filter(
      (e) => e.type !== "subagent_start" && e.type !== "subagent_end",
    );

    return (
      <SubAgentProvider value={true}>
        <Box flexDirection="column" marginTop={1}>
          <SessionHeader
            session={session}
            isRunning={isRunning}
            color={color}
            maxPromptLines={Infinity}
          />
          <Box flexDirection="column" marginLeft={3}>
            {innerEvents.map((e) => (
              <EventItem key={e.id} event={e} />
            ))}
          </Box>
          <SessionFooter session={session} />
        </Box>
      </SubAgentProvider>
    );
  }

  // ── Prompt mode: compact Claude Code format ────────────────────
  const toolLines = useMemo(() => {
    return sessionEvents
      .filter((e) => e.type === "tool_result" || e.type === "bash_result")
      .map((e) => compactToolLine(e.type, e.toolName, e.toolArgs, e.status, e.content));
  }, [sessionEvents]);

  const response = useMemo(() => {
    for (let i = sessionEvents.length - 1; i >= 0; i--) {
      const e = sessionEvents[i]!;
      if (e.type === "ai_message" && e.content.trim()) return e.content;
    }
    return null;
  }, [sessionEvents]);

  const visibleTools = toolLines.length > MAX_TOOL_LINES_COMPACT
    ? toolLines.slice(0, MAX_TOOL_LINES_COMPACT)
    : toolLines;
  const hiddenToolCount = toolLines.length - visibleTools.length;

  const resp = response ? truncText(response, MAX_RESPONSE_LINES_COMPACT) : null;

  return (
    <SubAgentProvider value={true}>
      <Box flexDirection="column" marginTop={1}>
        <SessionHeader
          session={session}
          isRunning={isRunning}
          color={color}
          maxPromptLines={0}
        />

        {/* Compact tool calls */}
        {visibleTools.map((line, i) => (
          <Text key={`t${i}`} dimColor>
            {`  ${GLYPH_HOOK}  ${line}`}
          </Text>
        ))}
        {hiddenToolCount > 0 && (
          <Text dimColor italic>{`  ${GLYPH_HOOK}  ... +${hiddenToolCount} more`}</Text>
        )}

        {/* Compact response */}
        {resp && (
          <>
            <Text dimColor>{`  ${GLYPH_HOOK}  Response:`}</Text>
            {resp.lines.map((line, i) => (
              <Text key={`r${i}`} dimColor wrap="wrap">
                {`       ${line}`}
              </Text>
            ))}
            {resp.truncated && (
              <Text dimColor italic>{"       ..."}</Text>
            )}
          </>
        )}

        <SessionFooter session={session} />
      </Box>
    </SubAgentProvider>
  );
});
