/* ── Agent Display Config & Dynamic Registry ──────────────────────────
 *
 * "Which agents exist" is determined by the backend (LangGraph Platform).
 * "How to display them" is determined by this frontend config.
 *
 * New agents added to langgraph.json appear automatically with default styling.
 * To customize, add an entry to AGENT_DISPLAY_CONFIG.
 */

// ── Types ──

export interface AgentDisplayMeta {
  name?: string;
  description?: string;
  role: string;
  color: string;
  imagePath?: string;
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  role: string;
  color: string;
  imagePath?: string;
  mascotEmoji?: string;
  /** Agent origin — reserved for future marketplace/plugin use */
  source?: "builtin" | "marketplace" | "custom";
  /** Searchable tags — reserved for future filtering */
  tags?: string[];
  /** Advertised capabilities — reserved for future UI */
  capabilities?: string[];
}

export interface KillChainPhase {
  role: string;
  label: string;
}

export interface KillChainGroup extends KillChainPhase {
  agents: AgentConfig[];
}

// ── Kill chain phase ordering ──

export const KILL_CHAIN_PHASES: KillChainPhase[] = [
  { role: "Orchestrator", label: "Orchestrator" },
  { role: "Planning", label: "Planning" },
  { role: "Reconnaissance", label: "Reconnaissance" },
  { role: "Exploitation", label: "Exploitation" },
  { role: "Post-Exploitation", label: "Post-Exploitation" },
  { role: "Analysis", label: "Analysis" },
  { role: "Domain Specialist", label: "Domain Specialists" },
  { role: "Vulnerability Research", label: "Vulnerability Research" },
];

// ── Display config (frontend-only visual metadata) ──

export const AGENT_DISPLAY_CONFIG: Record<string, AgentDisplayMeta> = {
  decepticon: {
    name: "Decepticon",
    description: "Main orchestrator — commands the full kill chain",
    role: "Orchestrator",
    color: "#ef4444",
    imagePath: "/agents/decepticon.png",
  },
  soundwave: {
    name: "Soundwave",
    description: "Socratic interview — generates RoE, CONOPS, OPPLAN",
    role: "Planning",
    color: "#8b5cf6",
  },
  recon: {
    name: "Recon",
    description: "Reconnaissance — port scanning, service enumeration",
    role: "Reconnaissance",
    color: "#3b82f6",
  },
  scanner: {
    name: "Scanner",
    description: "Vulnerability scanning — CVE detection, fingerprinting",
    role: "Reconnaissance",
    color: "#6366f1",
  },
  exploit: {
    name: "Exploit",
    description: "Initial access — exploit development and execution",
    role: "Exploitation",
    color: "#f59e0b",
  },
  exploiter: {
    name: "Exploiter",
    description: "PoC development — proof-of-concept exploit crafting",
    role: "Exploitation",
    color: "#d97706",
  },
  postexploit: {
    name: "Post-Exploit",
    description: "Persistence, lateral movement, privilege escalation",
    role: "Post-Exploitation",
    color: "#10b981",
  },
  vulnresearch: {
    name: "Vulnresearch",
    description: "Vulnerability research orchestrator — five-stage pipeline",
    role: "Vulnerability Research",
    color: "#dc2626",
  },
  analyst: {
    name: "Analyst",
    description: "Deep vulnerability analysis — SSRF, SQLi, XSS chains",
    role: "Analysis",
    color: "#f97316",
  },
  ad_operator: {
    name: "AD Operator",
    description: "Active Directory — BloodHound, Kerberos, ADCS attacks",
    role: "Domain Specialist",
    color: "#7c3aed",
  },
  cloud_hunter: {
    name: "Cloud Hunter",
    description: "Cloud security — AWS IAM, K8s, Terraform, metadata",
    role: "Domain Specialist",
    color: "#0ea5e9",
  },
  contract_auditor: {
    name: "Contract Auditor",
    description: "Smart contract security — Solidity, Slither, Foundry",
    role: "Domain Specialist",
    color: "#a855f7",
  },
  reverser: {
    name: "Reverser",
    description: "Binary analysis — strings, packers, ROP, symbols",
    role: "Domain Specialist",
    color: "#ec4899",
  },
  detector: {
    name: "Detector",
    description: "Vulnerability detection — pattern matching, triage",
    role: "Vulnerability Research",
    color: "#84cc16",
  },
  verifier: {
    name: "Verifier",
    description: "Vulnerability verification — confirms exploitability",
    role: "Vulnerability Research",
    color: "#64748b",
  },
  patcher: {
    name: "Patcher",
    description: "Patch proposal — generates and tests fixes",
    role: "Vulnerability Research",
    color: "#78716c",
  },
};

// ── Default display for unknown/new agents ──

const DEFAULT_DISPLAY: AgentDisplayMeta = {
  role: "Uncategorized",
  color: "#6b7280",
};

// ── Registry helpers ──

/** Merge a backend agent ID with frontend display config → full AgentConfig */
export function buildAgentConfig(
  id: string,
  backendMeta?: { description?: string },
): AgentConfig {
  const display = AGENT_DISPLAY_CONFIG[id] ?? DEFAULT_DISPLAY;
  return {
    id,
    name:
      display.name ||
      id
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase()),
    description: backendMeta?.description ?? display.description ?? "",
    role: display.role,
    color: display.color,
    imagePath: display.imagePath,
    source: "builtin",
  };
}

/** Group agents by kill chain phase, with unknown roles in "Uncategorized" */
export function groupByKillChain(agents: AgentConfig[]): KillChainGroup[] {
  const knownRoles = new Set(KILL_CHAIN_PHASES.map((p) => p.role));

  const groups: KillChainGroup[] = KILL_CHAIN_PHASES.map((phase) => ({
    ...phase,
    agents: agents.filter((a) => a.role === phase.role),
  }));

  const uncategorized = agents.filter((a) => !knownRoles.has(a.role));
  if (uncategorized.length > 0) {
    groups.push({
      role: "Uncategorized",
      label: "Uncategorized",
      agents: uncategorized,
    });
  }

  return groups.filter((g) => g.agents.length > 0);
}

// ── Static fallback (used when LangGraph server is unreachable) ──

export const AGENTS: AgentConfig[] = Object.keys(AGENT_DISPLAY_CONFIG).map(
  (id) => buildAgentConfig(id),
);

// ── Legacy helpers (backwards-compatible) ──

export function getAgent(id: string): AgentConfig | undefined {
  return AGENTS.find((a) => a.id === id);
}

export function getAgentsByRole(role: string): AgentConfig[] {
  return AGENTS.filter((a) => a.role === role);
}
