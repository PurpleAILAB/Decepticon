import * as fs from "fs";
import * as path from "path";
import { resolveCliEngagementDir } from "../lib/workspace.js";
import type { Command } from "./types.js";

const guide: Command = {
  name: "guide",
  description: "Provide live guidance to steer the active autonomous run",
  aliases: [],
  argumentHint: "<message>",
  execute(args, ctx) {
    const text = args.trim();
    if (!text) {
      ctx.addSystemEvent("Error: Please specify the guidance message. Usage: /guide <message>");
      return;
    }
    if (text.length > 1000) {
      ctx.addSystemEvent("Error: Guidance message exceeds maximum length of 1000 characters.");
      return;
    }

    // Bug fix (supersedes #636): write to the per-engagement subdir that
    // `GuidanceMiddleware._resolve_workspace_path` actually drains.
    const engagementDir = resolveCliEngagementDir();
    if (!engagementDir) {
      ctx.addSystemEvent(
        "Error: No active engagement (DECEPTICON_ENGAGEMENT is unset or invalid). " +
          "Re-launch via `decepticon start` to pick an engagement.",
      );
      return;
    }
    const guidanceDir = path.join(engagementDir, "guidance");
    const inboxPath = path.join(guidanceDir, "inbox.jsonl");

    try {
      fs.mkdirSync(guidanceDir, { recursive: true });
      const line = JSON.stringify({ text, timestamp: Date.now() / 1000 }) + "\n";
      fs.appendFileSync(inboxPath, line, "utf-8");
      ctx.addSystemEvent(`Guidance registered: "${text}"`);
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e);
      ctx.addSystemEvent(`Error: Failed to register guidance: ${err}`);
    }
  },
};

export default guide;
