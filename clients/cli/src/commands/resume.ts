import type { Command } from "./types.js";

const resume: Command = {
  name: "resume",
  description: "Resume a paused run with optional feedback",
  aliases: ["r"],
  argumentHint: "[feedback]",
  execute(args, ctx) {
    ctx.resume(args || undefined);
  },
};

export default resume;
