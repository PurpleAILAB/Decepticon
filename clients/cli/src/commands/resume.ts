import type { Command } from "./types.js";

const resume: Command = {
  name: "resume",
  description: "Resume paused run or continue previous session",
  aliases: ["r"],
  argumentHint: "[message]",
  execute(args, ctx) {
    ctx.resume(args || undefined);
  },
};

export default resume;
