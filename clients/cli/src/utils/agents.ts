/**
 * Display labels for agent names emitted by the backend.
 *
 * Backend emits snake_case names (e.g. "postexploit", "ad_operator").
 * Frontend converts via AGENT_LABELS for nice display.
 *
 * Unknown agents fall back to humanized (snake_case → Title Case).
 */

export const AGENT_LABELS: Record<string, string> = {
  // Orchestrator
  decepticon: "Decepticon",

  // Document generation
  soundwave: "Soundwave",

  // Kill chain
  recon: "Recon",
  exploit: "Exploit",
  postexploit: "PostExploit",

  // Specialist agents
  analyst: "Analyst",
  reverser: "Reverser",
  contract_auditor: "Contract Auditor",
  cloud_hunter: "Cloud Hunter",
  ad_operator: "AD Operator",
  vulnresearch: "VulnResearch",
  scanner: "Scanner",
  detector: "Detector",
  verifier: "Verifier",
  patcher: "Patcher",
  exploiter: "Exploiter",
  defender: "Defender",
};

/** Convert a backend agent name to its display label. */
export function labelForAgent(name: string | null | undefined): string {
  if (!name) return "idle";
  if (AGENT_LABELS[name]) return AGENT_LABELS[name];
  // Fallback: snake_case → Title Case
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
