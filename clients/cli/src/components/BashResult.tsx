import React from "react";
import { Box, Text } from "ink";
import { useScreen } from "./shell/ScreenContext.js";
import { useExpandOutput } from "./shell/ExpandOutputContext.js";
import { CtrlOToExpand } from "./shell/CtrlOToExpand.js";

interface BashResultProps {
  command: string;
  output: string;
  status?: "success" | "error";
}

const CWD_PATTERN = /\n?\[cwd: (.+?)\]\s*$/;
const MAX_OUTPUT_LINES_PROMPT = 8;
const MAX_OUTPUT_LINES_TRANSCRIPT = 200;

export const BashResult = React.memo(function BashResult({
  command,
  output,
  status,
}: BashResultProps) {
  const screen = useScreen();
  const isExpanded = useExpandOutput();

  // Extract [cwd: /path] metadata
  const cwdMatch = output.match(CWD_PATTERN);
  const cwd = cwdMatch?.[1] ?? "/workspace";
  const cleanOutput = cwdMatch
    ? output.slice(0, cwdMatch.index).trim()
    : output.trim();

  // Skip echo of command in first line
  const allLines = cleanOutput.split("\n");
  const outputLines =
    allLines[0]?.trim() === command.trim() ? allLines.slice(1) : allLines;

  // Detect error/info output
  const isError =
    status === "error" ||
    cleanOutput.startsWith("[ERROR]") ||
    cleanOutput.startsWith("[TIMEOUT]");
  const isInfo =
    cleanOutput.startsWith("[IDLE]") ||
    cleanOutput.startsWith("[RUNNING]") ||
    cleanOutput.startsWith("[BACKGROUND]");

  // Screen-aware truncation:
  // - transcript mode: generous limit
  // - prompt mode + expanded (latest output): generous limit
  // - prompt mode + collapsed: tight limit
  const maxLines =
    screen === "transcript" || isExpanded
      ? MAX_OUTPUT_LINES_TRANSCRIPT
      : MAX_OUTPUT_LINES_PROMPT;

  // Truncate very long output (60% head + 40% tail)
  const truncated = outputLines.length > maxLines;
  const headCount = Math.floor(maxLines * 0.6);
  const tailCount = maxLines - headCount;
  const displayLines = truncated
    ? [
        ...outputLines.slice(0, headCount),
        `... (${outputLines.length - maxLines} lines omitted)`,
        ...outputLines.slice(-tailCount),
      ]
    : outputLines;

  return (
    <Box flexDirection="column">
      <Text>
        <Text color="green" bold>{"┌──("}</Text>
        <Text color="red" bold>{"root㉿sandbox"}</Text>
        <Text color="green" bold>{")-["}</Text>
        <Text color="blue" bold>{cwd}</Text>
        <Text color="green" bold>{"]"}</Text>
      </Text>

      <Text>
        <Text color="green" bold>{"└─# "}</Text>
        <Text bold>{command}</Text>
      </Text>

      {displayLines
        .filter((l) => l !== "" || displayLines.length <= 3)
        .map((line, i) => (
          <Text
            key={i}
            color={isError ? "red" : isInfo ? "cyan" : undefined}
            dimColor={!isError && !isInfo}
          >
            {line}
          </Text>
        ))}

      {truncated && !isExpanded && <CtrlOToExpand />}
    </Box>
  );
});
