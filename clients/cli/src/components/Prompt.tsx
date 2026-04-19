import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { Box, Text, useInput } from "ink";
import { TextInput } from "@inkjs/ui";
import { useTerminalSize } from "../hooks/useTerminalSize.js";
import { useSpinnerFrame } from "../hooks/useSpinnerFrame.js";
import { getCommands } from "../commands/registry.js";
import { labelForAgent } from "../utils/agents.js";
import { CLI_VERSION } from "../utils/version.js";
import type { RunState } from "../hooks/useAgent.js";

interface PromptProps {
  runState: RunState;
  onSubmit: (input: string) => void;
  /** Currently active agent name, e.g. "recon". null when idle. */
  activeAgent?: string | null;
  /** Queued message waiting to be sent after stream completes. */
  queuedMessage?: string | null;
  /** Callback to update the queued message (for editing). */
  onEditQueue?: (message: string) => void;
}

const DEBOUNCE_MS = 150;

/** Compact status line: [Decepticon#1.0.0 | ActiveAgent] */
const StatusLine = React.memo(function StatusLine({
  activeAgent,
}: {
  activeAgent: string | null;
}) {
  const { tick } = useSpinnerFrame(activeAgent != null);
  // Blink cycle: bright for 8 ticks, dim for 4 ticks (only when active)
  const bright = activeAgent == null || (tick % 12) < 8;
  const label = labelForAgent(activeAgent);

  return (
    <Text>
      <Text dimColor>{"["}</Text>
      <Text dimColor>{`Decepticon#${CLI_VERSION}`}</Text>
      <Text dimColor>{" | "}</Text>
      {activeAgent ? (
        <Text color="#ef4444" bold={bright} dimColor={!bright}>
          {label}
        </Text>
      ) : (
        <Text dimColor>{label}</Text>
      )}
      <Text dimColor>{"]"}</Text>
    </Text>
  );
});

/** Context-sensitive keybinding hints. */
function KeybindingHints({ runState, hasQueue }: { runState: RunState; hasQueue: boolean }) {
  switch (runState) {
    case "streaming":
    case "connecting":
      return (
        <Text dimColor>
          {"  ctrl+o: expand  ctrl+c: pause  2x: cancel"}
        </Text>
      );
    case "paused":
      return (
        <Text dimColor>
          {"  ctrl+o: expand  ctrl+c: cancel  /resume: continue"}
        </Text>
      );
    default:
      return (
        <Text dimColor>
          {hasQueue
            ? "  ctrl+o: expand  ctrl+c: clear queue  esc: clear queue"
            : "  ctrl+o: expand  ctrl+c: exit"}
        </Text>
      );
  }
}

export const Prompt = React.memo(function Prompt({
  runState,
  onSubmit,
  activeAgent = null,
  queuedMessage = null,
  onEditQueue,
}: PromptProps) {
  const lastSubmitRef = useRef(0);
  const { columns } = useTerminalSize();
  const [inputValue, setInputValue] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [inputKey, setInputKey] = useState(0);

  const isActive = runState === "streaming" || runState === "connecting";

  // Derive autocomplete entries from command registry
  const commandEntries = useMemo(() => {
    const cmds = getCommands();
    const entries: { cmd: string; desc: string }[] = [];
    for (const c of cmds) {
      if (c.isHidden) continue;
      entries.push({ cmd: `/${c.name}`, desc: c.description });
      // Aliases work for execution but are hidden from autocomplete
    }
    return entries;
  }, []);

  // Filter commands — exclude exact matches (already fully typed)
  const isTypingCommand =
    inputValue.startsWith("/") && !inputValue.includes(" ");
  const filteredCommands = isTypingCommand
    ? commandEntries.filter(
        (c) => c.cmd.startsWith(inputValue) && c.cmd !== inputValue,
      )
    : [];
  const showMenu = filteredCommands.length > 0;

  // Reorder suggestions so selected dropdown item is first
  const suggestionList = showMenu
    ? [
        filteredCommands[selectedIdx]?.cmd,
        ...commandEntries.map((c) => c.cmd).filter(
          (c) => c !== filteredCommands[selectedIdx]?.cmd,
        ),
      ].filter((c): c is string => c != null)
    : commandEntries.map((c) => c.cmd);

  // Reset selection on input change
  useEffect(() => {
    setSelectedIdx(0);
  }, [inputValue]);

  // Up/Down/Tab — TextInput explicitly ignores these, so they bubble here
  useInput((_input, key) => {
    // Up arrow when queued + streaming: load queued message into input for editing
    if (key.upArrow && queuedMessage && isActive) {
      setInputValue(queuedMessage);
      setInputKey((prev) => prev + 1);
      return;
    }

    if (!showMenu) return;

    if (key.upArrow) {
      setSelectedIdx((prev) => Math.max(0, prev - 1));
    } else if (key.downArrow) {
      setSelectedIdx((prev) =>
        Math.min(filteredCommands.length - 1, prev + 1),
      );
    } else if (key.tab) {
      const cmd = filteredCommands[selectedIdx]?.cmd;
      if (cmd) {
        setInputValue(cmd);
        setInputKey((prev) => prev + 1);
      }
    }
  });

  const handleChange = useCallback((value: string) => {
    setInputValue(value);
  }, []);

  const handleSubmit = useCallback(
    (value: string) => {
      const now = Date.now();
      if (now - lastSubmitRef.current < DEBOUNCE_MS) return;
      lastSubmitRef.current = now;
      setInputValue("");
      setInputKey((prev) => prev + 1);

      // If streaming and not a slash command, update the queue
      if (isActive && onEditQueue && !value.startsWith("/")) {
        onEditQueue(value);
        return;
      }

      onSubmit(value);
    },
    [onSubmit, isActive, onEditQueue],
  );

  const maxCmdLen = Math.max(...commandEntries.map((c) => c.cmd.length));

  return (
    <Box flexDirection="column" marginTop={1}>
      {/* Queued message display */}
      {queuedMessage && isActive && (
        <Box marginLeft={2} marginBottom={0}>
          <Text dimColor italic>{"  "}{queuedMessage}</Text>
        </Box>
      )}

      <Text dimColor>{"─".repeat(columns)}</Text>
      <Box flexDirection="row">
        <Text color="white">{"› "}</Text>
        <TextInput
          key={inputKey}
          placeholder={queuedMessage && isActive ? "Press up to edit queued message" : ""}
          defaultValue={inputValue || undefined}
          suggestions={suggestionList}
          isDisabled={false}
          onChange={handleChange}
          onSubmit={handleSubmit}
        />
      </Box>

      <Text dimColor>{"─".repeat(columns)}</Text>

      {/* Autocomplete menu — below the input divider, Claude Code style */}
      {showMenu && (
        <Box flexDirection="column" marginLeft={2}>
          {filteredCommands.map((cmd, i) => (
            <Text key={cmd.cmd}>
              <Text
                bold={i === selectedIdx}
                dimColor={i !== selectedIdx}
              >
                {` ${cmd.cmd.padEnd(maxCmdLen + 2)}`}
              </Text>
              <Text dimColor>{cmd.desc}</Text>
            </Text>
          ))}
        </Box>
      )}

      {/* Compact status line — always visible */}
      <StatusLine activeAgent={activeAgent} />

      {/* Context-sensitive keybinding hints */}
      <KeybindingHints runState={runState} hasQueue={queuedMessage != null} />
    </Box>
  );
});
