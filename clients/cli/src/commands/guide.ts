import * as fs from "fs";
import * as path from "path";
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

    const workspace = process.env.DECEPTICON_WORKSPACE_PATH ?? "/workspace";
    const guidanceDir = path.join(workspace, "guidance");
    const inboxPath = path.join(guidanceDir, "inbox.jsonl");

    try {
      if (!fs.existsSync(guidanceDir)) {
        fs.mkdirSync(guidanceDir, { recursive: true });
      }
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
