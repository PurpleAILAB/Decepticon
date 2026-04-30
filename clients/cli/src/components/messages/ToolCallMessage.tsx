import React from "react";
import { Box, Text } from "ink";
import type { AgentEvent } from "../../types.js";
import { shortPath, extractSkillName, truncateLines } from "../../utils/format.js";
import { TodoList, parseTodos } from "../TodoList.js";
import { DiffResult } from "./DiffResult.js";
import { useScreen } from "../shell/ScreenContext.js";
import { CtrlOToExpand } from "../shell/CtrlOToExpand.js";
import { GLYPH_DOT, GLYPH_HOOK } from "../../utils/theme.js";

const MAX_LINES_PROMPT = 5;
const MAX_LINES_TRANSCRIPT = 50;

// ── OPPLAN tools — suppressed from scrolling history ─────────────
const OPPLAN_TOOLS = new Set([
  "add_objective",
  "get_objective",
  "list_objectives",
  "update_objective",
]);

// ── Friendly tool display names ───────────────────────────────────
const TOOL_DISPLAY: Record<string, string> = {
  read_file: "Read",
  write_file: "Write",
  edit_file: "Edit",
  ls: "List",
  glob: "Glob",
  grep: "Grep",
  execute: "Execute",
  write_todos: "Todos",
  ask_user_question: "Ask",
  complete_engagement_planning: "Plan complete",
  load_skill: "Skill",
};

// ── Tool call header ──────────────────────────────────────────────

function ToolCallHeader({
  toolName,
  args,
  status,
}: {
  toolName: string;
  args: Record<string, unknown>;
  status?: "success" | "error";
}) {
  const label = TOOL_DISPLAY[toolName];
  const dotColor = status === "error" ? "red" : "green";

  if (!label) {
    const argsStr = Object.entries(args)
      .filter(([, v]) => v != null && v !== "")
      .map(([k, v]) => {
        const val = typeof v === "string" ? `"${v}"` : String(v);
        return `${k}=${val}`;
      })
      .join(", ");
    return (
      <Text>
        <Text color={dotColor}>{`${GLYPH_DOT} `}</Text>
        <Text color="white" bold>{toolName}</Text>
        <Text color="gray" italic>{` (${argsStr})`}</Text>
      </Text>
    );
  }

  let detail = "";
  let detailDim = "";

  switch (toolName) {
    case "read_file": {
      const filePath = shortPath((args.file_path as string) ?? "");
      detail = filePath;
      const offset = Number(args.offset ?? 0);
      const limit = Number(args.limit ?? 100);
      if (offset > 0 || limit !== 100) {
        detailDim = ` lines ${offset + 1}-${offset + limit}`;
      }
      break;
    }
    case "load_skill": {
      detail = (args.skill_path as string) ?? "";
      if (args.include_siblings === true) detailDim = " +siblings";
      break;
    }
    case "write_file":
    case "edit_file":
      detail = shortPath((args.file_path as string) ?? "");
      break;
    case "ls":
      detail = shortPath((args.path as string) ?? "/");
      break;
    case "glob": {
      detail = (args.pattern as string) ?? "";
      const globPath = (args.path as string) ?? "/";
      if (globPath !== "/") detailDim = ` in ${shortPath(globPath)}`;
      break;
    }
    case "grep": {
      detail = (args.pattern as string) ?? "";
      const grepPath = args.path as string | undefined;
      const globFilter = args.glob as string | undefined;
      if (grepPath) detailDim = ` in ${shortPath(grepPath)}`;
      if (globFilter) detailDim += ` [${globFilter}]`;
      break;
    }
    case "execute": {
      let cmd = (args.command as string) ?? "";
      if (cmd.length > 80) cmd = cmd.slice(0, 77) + "...";
      detail = cmd;
      break;
    }
    case "write_todos":
      break;
  }

  return (
    <Text>
      <Text color={dotColor}>{`${GLYPH_DOT} `}</Text>
      <Text color="white" bold>{label}</Text>
      {detail ? <Text color="gray" italic>{` (${detail})`}</Text> : null}
      {detailDim ? <Text color="gray" italic>{detailDim}</Text> : null}
    </Text>
  );
}

// ── Result content ────────────────────────────────────────────────

function ResultContent({
  content,
  maxLines,
}: {
  content: string;
  maxLines: number;
}) {
  const display = truncateLines(content, maxLines);
  const wasTruncated = content.split("\n").length > maxLines;
  return (
    <>
      {display.map((line, i) => (
        <Text key={i} dimColor wrap="wrap">
          {i === 0 ? `  ${GLYPH_HOOK}  ` : "     "}{line}
        </Text>
      ))}
      {wasTruncated && <CtrlOToExpand />}
    </>
  );
}

// ── Main component ────────────────────────────────────────────────

interface Props {
  event: AgentEvent;
}

export const ToolCallMessage = React.memo(function ToolCallMessage({
  event,
}: Props) {
  const screen = useScreen();
  const maxLines = screen === "transcript" ? MAX_LINES_TRANSCRIPT : MAX_LINES_PROMPT;

  // Skill reads — show just the skill name
  const skillName = extractSkillName(event.toolArgs ?? {});
  if (skillName) {
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text>
          <Text color="green">{`${GLYPH_DOT} `}</Text>
          <Text color="white" bold>{"Skill"}</Text>
          <Text color="gray" italic>{` (${skillName})`}</Text>
        </Text>
      </Box>
    );
  }

  // write_todos — render as checklist
  if (event.toolName === "write_todos") {
    const todos = parseTodos(event.toolArgs ?? {});
    if (todos.length > 0) {
      return (
        <Box flexDirection="column" marginTop={1}>
          <ToolCallHeader
            toolName="write_todos"
            args={event.toolArgs ?? {}}
            status={event.status}
          />
          <TodoList todos={todos} />
        </Box>
      );
    }
  }

  // OPPLAN tools — suppress from history
  if (OPPLAN_TOOLS.has(event.toolName ?? "")) {
    return null;
  }

  // edit_file — Claude Code-style diff display
  if (event.toolName === "edit_file") {
    const args = event.toolArgs ?? {};
    const filePath = (args.file_path as string) ?? "";
    const oldString = (args.old_string as string) ?? "";
    const newString = (args.new_string as string) ?? "";
    if (filePath && (oldString || newString)) {
      return (
        <DiffResult
          filePath={filePath}
          oldString={oldString}
          newString={newString}
          status={event.status}
          content={event.content}
        />
      );
    }
  }

  return (
    <Box flexDirection="column" marginTop={1}>
      <ToolCallHeader
        toolName={event.toolName ?? ""}
        args={event.toolArgs ?? {}}
        status={event.status}
      />
      <ResultContent content={event.content} maxLines={maxLines} />
    </Box>
  );
});
