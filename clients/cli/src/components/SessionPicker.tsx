/**
 * SessionPicker — Interactive session resume UI (Claude Code style).
 *
 * Shows a searchable list of previous sessions. Arrow keys to navigate,
 * Enter to select, Escape to cancel.
 */

import React, { useState, useMemo } from "react";
import { Box, Text, useInput } from "ink";
import { useTerminalSize } from "../hooks/useTerminalSize.js";
import type { ThreadEntry } from "../utils/threadStore.js";

interface SessionPickerProps {
  sessions: ThreadEntry[];
  onSelect: (session: ThreadEntry) => void;
  onCancel: () => void;
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minute${mins !== 1 ? "s" : ""} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours !== 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days !== 1 ? "s" : ""} ago`;
}

export const SessionPicker = React.memo(function SessionPicker({
  sessions,
  onSelect,
  onCancel,
}: SessionPickerProps) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [search, setSearch] = useState("");
  const { columns } = useTerminalSize();

  const filtered = useMemo(() => {
    if (!search) return sessions;
    const q = search.toLowerCase();
    return sessions.filter((s) => s.title.toLowerCase().includes(q));
  }, [sessions, search]);

  useInput((input, key) => {
    if (key.escape) {
      onCancel();
      return;
    }
    if (key.return) {
      const session = filtered[selectedIdx];
      if (session) onSelect(session);
      return;
    }
    if (key.upArrow) {
      setSelectedIdx((prev) => Math.max(0, prev - 1));
      return;
    }
    if (key.downArrow) {
      setSelectedIdx((prev) => Math.min(filtered.length - 1, prev + 1));
      return;
    }
    if (key.backspace || key.delete) {
      setSearch((prev) => prev.slice(0, -1));
      setSelectedIdx(0);
      return;
    }
    // Printable character — append to search
    if (input && !key.ctrl && !key.meta) {
      setSearch((prev) => prev + input);
      setSelectedIdx(0);
    }
  });

  const maxVisible = 10;
  const startIdx = Math.max(0, selectedIdx - maxVisible + 1);
  const visibleSessions = filtered.slice(startIdx, startIdx + maxVisible);
  const total = filtered.length;

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text dimColor>{"─".repeat(columns)}</Text>

      {/* Header */}
      <Box marginLeft={1}>
        <Text bold>Resume Session</Text>
        <Text dimColor>{` (${selectedIdx + 1} of ${total})`}</Text>
      </Box>

      {/* Search box */}
      <Box marginLeft={1} marginTop={0}>
        <Text dimColor>{"Search: "}</Text>
        <Text>{search || ""}</Text>
        <Text dimColor>{search ? "" : "(type to filter)"}</Text>
      </Box>

      {/* Session list */}
      <Box flexDirection="column" marginTop={1} marginLeft={1}>
        {visibleSessions.length === 0 ? (
          <Text dimColor>  No sessions found.</Text>
        ) : (
          visibleSessions.map((session, i) => {
            const globalIdx = startIdx + i;
            const isSelected = globalIdx === selectedIdx;
            const timeAgo = formatTimeAgo(session.lastUsed);
            const title = session.title.length > 70
              ? session.title.slice(0, 67) + "..."
              : session.title;

            return (
              <Box key={session.threadId} flexDirection="column">
                <Text>
                  <Text color={isSelected ? "red" : undefined} bold={isSelected}>
                    {isSelected ? ">" : " "}{" "}
                  </Text>
                  <Text bold={isSelected} color={isSelected ? "white" : undefined}>
                    {title}
                  </Text>
                </Text>
                <Text dimColor>
                  {"    "}{timeAgo}
                </Text>
              </Box>
            );
          })
        )}
      </Box>

      {/* Footer hints */}
      <Box marginTop={1} marginLeft={1}>
        <Text dimColor>
          {"Enter to select \u00B7 Esc to cancel \u00B7 Type to search"}
        </Text>
      </Box>

      <Text dimColor>{"─".repeat(columns)}</Text>
    </Box>
  );
});
