/**
 * /plugins — runtime plugin bundle enable/disable.
 *
 * OSS default loads the ``standard`` bundle only (10 official agents).
 * The ``plugins`` bundle ships extras (vulnresearch orchestrator + its
 * 5 specialists) but is off by default. /plugins lets the operator
 * toggle bundles without restarting the langgraph container — the
 * langgraph platform exposes a custom HTTP surface under
 * ``/_decepticon/bundles`` that calls ``register_graph()`` at runtime.
 *
 * Usage:
 *   /plugins                  Show every bundle + enabled state
 *   /plugins enable <name>    Activate every graph in the bundle
 *   /plugins disable <name>   Drop every graph in the bundle
 *
 * Enabling a bundle adds its orchestrator(s) to the /agent switcher.
 * For ``plugins`` that means ``vulnresearch`` becomes selectable.
 *
 * Persistence: runtime-only. Bundles activated here do NOT survive a
 * ``decepticon restart``. To make a selection permanent, set
 * ``DECEPTICON_PLUGINS=standard,plugins`` in ``~/.decepticon/.env``.
 */

import type { Command } from "./types.js";

interface BundleStatus {
  name: string;
  enabled: boolean;
  graphs: string[];
}

interface ListResponse {
  bundles: BundleStatus[];
}

interface ToggleResponse {
  bundle: string;
  enabled: boolean;
  graphs: string[];
  skipped: string[];
}

function apiBase(): string {
  return process.env.DECEPTICON_API_URL || "http://localhost:2024";
}

function formatList(data: ListResponse): string {
  const lines: string[] = ["Available plugin bundles:", ""];
  for (const b of data.bundles) {
    const mark = b.enabled ? "[on] " : "[off]";
    lines.push(`  ${mark} ${b.name}  (${b.graphs.length} graphs)`);
    for (const g of b.graphs) {
      lines.push(`         - ${g}`);
    }
  }
  lines.push("");
  lines.push("Usage:");
  lines.push("  /plugins enable <name>    Activate the bundle (runtime, no restart)");
  lines.push("  /plugins disable <name>   Drop the bundle");
  lines.push("  /agent <orchestrator>     Switch active orchestrator after enabling");
  lines.push("");
  lines.push(
    "Activations are runtime-only. To persist across `decepticon restart`,",
  );
  lines.push("set DECEPTICON_PLUGINS in ~/.decepticon/.env (e.g. standard,plugins).");
  return lines.join("\n");
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed?.detail) detail = String(parsed.detail);
    } catch {
      // not JSON — surface raw text
    }
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

const plugins: Command = {
  name: "plugins",
  description: "List or toggle agent plugin bundles",
  argumentHint: "[enable|disable <bundle>]",
  aliases: ["plugin", "플러그인"],
  execute(args, ctx) {
    const parts = args.trim().split(/\s+/).filter(Boolean);
    const sub = parts[0]?.toLowerCase() ?? "";

    // /plugins (no args) — list current state
    if (!sub) {
      void (async () => {
        try {
          const data = await getJson<ListResponse>(`${apiBase()}/_decepticon/bundles`);
          ctx.addSystemEvent(formatList(data));
        } catch (err) {
          ctx.addSystemEvent(
            `Could not reach plugin bundles API at ${apiBase()}: ${err instanceof Error ? err.message : String(err)}\n` +
              "Is the decepticon stack running?",
          );
        }
      })();
      return;
    }

    if (sub !== "enable" && sub !== "disable") {
      ctx.addSystemEvent(
        `Unknown subcommand '${sub}'. Use /plugins, /plugins enable <name>, or /plugins disable <name>.`,
      );
      return;
    }

    const bundle = parts[1]?.trim() ?? "";
    if (!bundle) {
      ctx.addSystemEvent(`Missing bundle name. Try: /plugins ${sub} plugins`);
      return;
    }

    void (async () => {
      try {
        const url = `${apiBase()}/_decepticon/bundles/${encodeURIComponent(bundle)}/${sub}`;
        const data = await getJson<ToggleResponse>(url, { method: "POST" });

        const verb = sub === "enable" ? "enabled" : "disabled";
        const lines: string[] = [
          `Bundle '${data.bundle}' ${verb}.`,
        ];
        if (data.graphs.length > 0) {
          lines.push(`  ${verb === "enabled" ? "Registered" : "Removed"}: ${data.graphs.join(", ")}`);
        }
        if (data.skipped.length > 0) {
          lines.push(
            `  Skipped (already ${verb === "enabled" ? "active" : "absent"}): ${data.skipped.join(", ")}`,
          );
        }
        if (verb === "enabled" && data.bundle === "plugins") {
          lines.push("");
          lines.push("Tip: switch to the new orchestrator with `/agent vulnresearch`.");
        }
        ctx.addSystemEvent(lines.join("\n"));
      } catch (err) {
        ctx.addSystemEvent(
          `Failed to ${sub} bundle '${bundle}': ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
  },
};

export default plugins;
