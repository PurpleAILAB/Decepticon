import React from "react";
import { Box, Text } from "ink";
import { GLYPH_DOT } from "../../utils/theme.js";

interface Props {
  command?: string;
  session?: string;
  exitCode: number | null | undefined;
  elapsed?: number;
  output: string;
}

/**
 * Renders a Claude-Code-style background-job completion notice.
 *
 *     ● Background command "nmap -sV target" completed (exit code 0) — session=scan · 12.3s
 *       <captured output, dim, wrap-on>
 *
 * The output is emitted by ``SandboxNotificationMiddleware`` (already
 * truncated to a head+tail preview when large) so the operator sees the
 * full bash_output result without the agent having to fetch it.
 */
export const BackgroundCompleteMessage = React.memo(
  function BackgroundCompleteMessage({
    command,
    session,
    exitCode,
    elapsed,
    output,
  }: Props) {
    const failed = exitCode !== 0 && exitCode !== null && exitCode !== undefined;
    const exitStr =
      exitCode === null || exitCode === undefined
        ? ""
        : ` (exit code ${exitCode})`;
    const tail: string[] = [];
    if (session) tail.push(`session=${session}`);
    if (typeof elapsed === "number") tail.push(`${elapsed.toFixed(1)}s`);
    const suffix = tail.length > 0 ? ` — ${tail.join(" · ")}` : "";

    return (
      <Box marginTop={1} flexDirection="column">
        <Text color={failed ? "red" : "green"}>
          {GLYPH_DOT} <Text bold>Background command</Text>
          {command ? ` "${command}"` : ""} completed{exitStr}
          <Text dimColor>{suffix}</Text>
        </Text>
        {output ? (
          <Box marginLeft={2} marginTop={0}>
            <Text dimColor wrap="wrap">
              {output}
            </Text>
          </Box>
        ) : null}
      </Box>
    );
  },
);
