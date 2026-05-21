/**
 * /agent — switch the active orchestrator for this CLI session.
 *
 * Only orchestration agents are surfaced here. Sub-agents (recon,
 * exploit, postexploit, …) are invoked via the orchestrator's task()
 * tool and shouldn't be selected directly. The whitelist below pins the
 * two orchestrators OSS ships:
 *
 *   - decepticon   — standard bundle. Always available.
 *   - vulnresearch — plugins bundle. Available once enabled via /plugins.
 *
 * Selection writes to the per-process assistant override (see
 * commands/assistantOverride.ts) which useAgent reads on every submit()
 * / resume(), beating the default INITIAL_ASSISTANT_ID and the
 * soundwave→decepticon in-flight handoff. The choice persists for the
 * lifetime of this CLI process.
 *
 * Usage:
 *   /agent              List orchestrators + current selection
 *   /agent <name>       Switch to the named orchestrator
 *   /agent clear        Clear the override (resume default behaviour)
 */

import type { Command } from "./types.js";
import {
  getAssistantOverride,
  setAssistantOverride,
} from "./assistantOverride.js";

const ORCHESTRATOR_ALLOWLIST = ["decepticon", "vulnresearch"] as const;
type Orchestrator = (typeof ORCHESTRATOR_ALLOWLIST)[number];

interface AssistantRow {
  assistant_id: string;
  graph_id: string;
  name: string;
}

function apiBase(): string {
  return process.env.DECEPTICON_API_URL || "http://localhost:2024";
}

async function listOrchestrators(): Promise<Orchestrator[]> {
  const res = await fetch(`${apiBase()}/assistants/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    throw new Error(`assistants/search HTTP ${res.status}: ${await res.text()}`);
  }
  const data = (await res.json()) as AssistantRow[];
  const registered = new Set(data.map((a) => a.graph_id));
  return ORCHESTRATOR_ALLOWLIST.filter((g) => registered.has(g));
}

const agent: Command = {
  name: "agent",
  description: "Show or switch the active orchestrator for this session",
  argumentHint: "[<name> | clear]",
  execute(args, ctx) {
    const arg = args.trim();

    // No arg → list orchestrators + current override
    if (!arg) {
      void (async () => {
        try {
          const orchestrators = await listOrchestrators();
          const current = getAssistantOverride();
          const lines: string[] = [];
          if (current) {
            lines.push(`Active orchestrator override: ${current}`);
          } else {
            lines.push(
              "No override active — using the default orchestrator selection (decepticon, or soundwave→decepticon handoff).",
            );
          }
          lines.push("");
          lines.push("Available orchestrators:");
          if (orchestrators.length === 0) {
            lines.push("  (none — is the langgraph stack up?)");
          } else {
            for (const o of orchestrators) {
              const mark = o === current ? "*" : " ";
              lines.push(`  ${mark} ${o}`);
            }
          }
          if (!orchestrators.includes("vulnresearch")) {
            lines.push("");
            lines.push(
              "Tip: vulnresearch ships in the 'plugins' bundle. Enable with `/plugins enable plugins`.",
            );
          }
          lines.push("");
          lines.push("Usage:");
          lines.push("  /agent <name>     Switch (e.g. /agent vulnresearch)");
          lines.push("  /agent clear      Drop the override, resume default behaviour");
          ctx.addSystemEvent(lines.join("\n"));
        } catch (err) {
          ctx.addSystemEvent(
            `Could not list orchestrators: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      })();
      return;
    }

    // Clear
    if (arg === "clear" || arg === "off" || arg === "none") {
      const prev = getAssistantOverride();
      setAssistantOverride("");
      ctx.addSystemEvent(
        prev
          ? `Orchestrator override cleared (was '${prev}'). Default behaviour resumes on next message.`
          : "No override was set.",
      );
      return;
    }

    // Switch
    if (!ORCHESTRATOR_ALLOWLIST.includes(arg as Orchestrator)) {
      ctx.addSystemEvent(
        `'${arg}' is not a known orchestrator. Valid options: ${ORCHESTRATOR_ALLOWLIST.join(", ")}.`,
      );
      return;
    }

    void (async () => {
      try {
        const orchestrators = await listOrchestrators();
        if (!orchestrators.includes(arg as Orchestrator)) {
          ctx.addSystemEvent(
            `'${arg}' isn't currently registered with the agent runtime. ` +
              (arg === "vulnresearch"
                ? "Enable its bundle first: /plugins enable plugins"
                : "Check that the agent stack is running."),
          );
          return;
        }
        setAssistantOverride(arg);
        ctx.addSystemEvent(
          `Active orchestrator: ${arg}\nNext message routes here. Type /agent clear to revert.`,
        );
      } catch (err) {
        ctx.addSystemEvent(
          `Failed to switch orchestrator: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
  },
};

export default agent;
