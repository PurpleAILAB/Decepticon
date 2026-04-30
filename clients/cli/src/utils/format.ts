/** Strip /workspace/ prefix for concise display. */
export function shortPath(path: string): string {
  if (path.startsWith("/workspace/")) return path.slice("/workspace/".length);
  if (path === "/workspace") return "/";
  return path;
}

/** Format milliseconds as human-readable duration (e.g. "1m 23s", "45s"). */
export function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
}

/** Format large numbers with K/M suffixes (e.g. 1500 → "1.5K"). */
export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/** Extract skill name from a /skills/... path. Returns null if not a skill path.
 *  Recognizes both `read_file({file_path})` and `load_skill({skill_path})`. */
export function extractSkillName(args: Record<string, unknown>): string | null {
  const filePath =
    (args.skill_path as string | undefined) ??
    (args.file_path as string | undefined);
  if (!filePath || !filePath.includes("/skills/")) return null;
  const parts = filePath.split("/");
  const skillsIdx = parts.indexOf("skills");
  const skillDir = parts[parts.length - 2];
  if (skillDir && skillDir !== "skills" && skillsIdx >= 0) return skillDir;
  return parts[skillsIdx + 1] ?? null;
}

/** Truncate content lines for display. */
export function truncateLines(content: string, maxLines: number): string[] {
  const lines = content.split("\n");
  if (lines.length <= maxLines) return lines;
  return [
    ...lines.slice(0, maxLines),
    `... (${lines.length - maxLines} more lines)`,
  ];
}

// ── Compact tool display names ────────────────────────────────────

const COMPACT_TOOL: Record<string, string> = {
  read_file: "Read",
  write_file: "Write",
  edit_file: "Update",
  ls: "List",
  glob: "Glob",
  grep: "Grep",
  execute: "Bash",
};

/**
 * Generate a compact tool call string for sub-agent activity display.
 *
 * Examples:
 *   Bash(nmap -sV 192.168.1.1)
 *   Read(/workspace/recon/nmap.txt)
 *   Grep(open.*port)
 *   Error: EISDIR: illegal operation on a directory
 */
export function compactToolLine(
  type: string,
  toolName?: string,
  toolArgs?: Record<string, unknown>,
  status?: string,
  content?: string,
): string {
  // Error → show error message
  if (status === "error" && content) {
    const firstLine = content.split("\n")[0] ?? "";
    return `Error: ${firstLine.length > 80 ? firstLine.slice(0, 77) + "..." : firstLine}`;
  }

  // Bash result
  if (type === "bash_result") {
    let cmd = (toolArgs?.command as string) ?? "";
    if (cmd.length > 60) cmd = cmd.slice(0, 57) + "...";
    return `Bash(${cmd})`;
  }

  // Known tools
  const label = COMPACT_TOOL[toolName ?? ""];
  if (label) {
    const arg = primaryArg(toolName!, toolArgs ?? {});
    return arg ? `${label}(${arg})` : label;
  }

  // Unknown tool — show name + first arg
  if (toolName) {
    const entries = Object.entries(toolArgs ?? {}).filter(
      ([, v]) => v != null && v !== "",
    );
    if (entries.length > 0) {
      const val = String(entries[0]![1]);
      return `${toolName}(${val.length > 50 ? val.slice(0, 47) + "..." : val})`;
    }
    return toolName;
  }

  return "Unknown tool";
}

/** Extract the primary display argument for a known tool. */
function primaryArg(
  toolName: string,
  args: Record<string, unknown>,
): string {
  let val = "";
  switch (toolName) {
    case "read_file":
    case "write_file":
    case "edit_file":
      val = shortPath((args.file_path as string) ?? "");
      break;
    case "ls":
      val = shortPath((args.path as string) ?? "/");
      break;
    case "glob":
      val = (args.pattern as string) ?? "";
      break;
    case "grep":
      val = (args.pattern as string) ?? "";
      break;
    case "execute": {
      const cmd = (args.command as string) ?? "";
      val = cmd.length > 60 ? cmd.slice(0, 57) + "..." : cmd;
      break;
    }
  }
  return val;
}
