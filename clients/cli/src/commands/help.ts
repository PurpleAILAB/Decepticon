import type { Command } from "./types.js";
import { getCommands } from "./registry.js";

const help: Command = {
  name: "help",
  description: "Show available commands and shortcuts",
  aliases: ["?"],
  execute(_args, ctx) {
    const commands = getCommands();
    const visible = commands.filter((c) => !c.isHidden);
    const maxLen = Math.max(...visible.map((c) => c.name.length + (c.argumentHint?.length ?? 0) + 1));

    const lines = [
      "Commands:",
      ...visible.map((c) => {
        const usage = c.argumentHint ? `/${c.name} ${c.argumentHint}` : `/${c.name}`;
        return `  ${usage.padEnd(maxLen + 4)}${c.description}`;
      }),
      "",
      "Shortcuts:",
      "  ctrl+o  Expand (toggle transcript view)",
      "  ctrl+c  Pause stream (1x) / cancel (2x) / exit (idle)",
      "  Esc     Exit transcript / clear queue",
    ];

    ctx.addSystemEvent(lines.join("\n"));
  },
};

export default help;
