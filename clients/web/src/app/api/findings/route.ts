import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { resolveEngagementDir } from "@/lib/workspace";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TriageStatus = "open" | "confirmed" | "false_positive" | "remediated" | "accepted_risk";

const VALID_TRIAGE_STATUSES: ReadonlySet<string> = new Set<TriageStatus>([
  "open",
  "confirmed",
  "false_positive",
  "remediated",
  "accepted_risk",
]);

interface Finding {
  id: string;
  title: string;
  severity: string;
  description: string;
  evidence: string;
  attackVector: string;
  affectedAssets: string[];
  cvssScore?: number;
  cvssVector?: string;
  cwe?: string[];
  mitre?: string[];
  remediation?: string;
  engagementId: string;
  engagementName: string;
  triageStatus: TriageStatus;
  triageNote?: string;
}

interface TriageState {
  [findingId: string]: {
    status: TriageStatus;
    note?: string;
    updatedAt: string;
  };
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

const WORKSPACE =
  process.env.WORKSPACE_PATH ??
  path.join(process.env.HOME ?? "", ".decepticon", "workspace");

// ---------------------------------------------------------------------------
// Markdown parser (same algorithm as engagement-scoped route)
// ---------------------------------------------------------------------------

function parseFindingMarkdown(
  content: string,
  filename: string,
): Omit<Finding, "engagementId" | "engagementName" | "triageStatus" | "triageNote"> {
  const lines = content.split("\n");
  let title = filename;
  let severity = "medium";
  let description = "";
  let evidence = "";
  let attackVector = "";
  const affectedAssets: string[] = [];
  let cvssScore: number | undefined;
  let cvssVector: string | undefined;
  const cwe: string[] = [];
  const mitre: string[] = [];
  let remediation = "";
  let currentSection = "";

  for (const line of lines) {
    const heading = /^##\s+(.+)/.exec(line);
    if (heading) {
      currentSection = heading[1].toLowerCase().trim();
      continue;
    }
    const h1 = /^#\s+(.+)/.exec(line);
    if (h1) {
      title = h1[1].trim();
      continue;
    }

    const metaMatch = /^\*\*(\w[\w\s]*)\*\*:\s*(.+)/.exec(line);
    if (metaMatch) {
      const key = metaMatch[1].toLowerCase().trim();
      const val = metaMatch[2].trim();
      switch (key) {
        case "severity":
          severity = val.toLowerCase();
          break;
        case "cvss score":
        case "cvss": {
          const parsed = parseFloat(val);
          if (!Number.isNaN(parsed)) cvssScore = parsed;
          break;
        }
        case "cvss vector":
          cvssVector = val;
          break;
        case "attack vector":
          attackVector = val;
          break;
        case "cwe":
          cwe.push(...val.split(",").map((c) => c.trim()).filter(Boolean));
          break;
        case "mitre":
        case "mitre att&ck":
          mitre.push(...val.split(",").map((m) => m.trim()).filter(Boolean));
          break;
      }
      continue;
    }

    const trimmed = line.trim();
    if (!trimmed) continue;
    const asset = /^[-*]\s+(.+)/.exec(trimmed);

    switch (currentSection) {
      case "description":
        description += (description ? "\n" : "") + trimmed;
        break;
      case "evidence":
        evidence += (evidence ? "\n" : "") + trimmed;
        break;
      case "affected assets":
      case "assets":
        if (asset) affectedAssets.push(asset[1].trim());
        break;
      case "remediation":
      case "recommendation":
        remediation += (remediation ? "\n" : "") + trimmed;
        break;
    }
  }

  const id = filename.replace(/\.md$/i, "");

  return {
    id,
    title,
    severity,
    description,
    evidence,
    attackVector,
    affectedAssets,
    cvssScore,
    cvssVector,
    cwe: cwe.length > 0 ? cwe : undefined,
    mitre: mitre.length > 0 ? mitre : undefined,
    remediation: remediation || undefined,
  };
}

// ---------------------------------------------------------------------------
// Triage state persistence
// ---------------------------------------------------------------------------

function triageFilePath(engDir: string): string {
  return path.join(engDir, ".triage.json");
}

async function loadTriageState(engDir: string): Promise<TriageState> {
  try {
    const raw = await fs.readFile(triageFilePath(engDir), "utf-8");
    return JSON.parse(raw) as TriageState;
  } catch {
    return {};
  }
}

async function saveTriageState(engDir: string, state: TriageState): Promise<void> {
  await fs.writeFile(triageFilePath(engDir), JSON.stringify(state, null, 2), "utf-8");
}

// ---------------------------------------------------------------------------
// GET /api/findings?engagementId=…
// ---------------------------------------------------------------------------

export async function GET(req: NextRequest) {
  try {
    const { userId } = await requireAuth();

    const engagementIdFilter = req.nextUrl.searchParams.get("engagementId");
    const engagements = await prisma.engagement.findMany({
      where: engagementIdFilter
        ? { id: engagementIdFilter, userId }
        : { userId },
    });

    const allFindings: Finding[] = [];

    for (const eng of engagements) {
      let engDir: string;
      try {
        engDir = resolveEngagementDir(eng.name, WORKSPACE);
      } catch {
        continue;
      }

      const findingsDir = path.join(engDir, "findings");
      let files: string[];
      try {
        files = (await fs.readdir(findingsDir)).filter((f) =>
          f.endsWith(".md"),
        );
      } catch {
        continue;
      }

      const triageState = await loadTriageState(engDir);

      for (const file of files) {
        try {
          const content = await fs.readFile(path.join(findingsDir, file), "utf-8");
          const parsed = parseFindingMarkdown(content, file);
          const triage = triageState[parsed.id];
          allFindings.push({
            ...parsed,
            engagementId: eng.id,
            engagementName: eng.name,
            triageStatus: (triage?.status as TriageStatus) ?? "open",
            triageNote: triage?.note,
          });
        } catch {
          // Skip malformed files
        }
      }
    }

    // Default sort: critical first
    allFindings.sort((a, b) => {
      const order: Record<string, number> = {
        critical: 0,
        high: 1,
        medium: 2,
        low: 3,
        informational: 4,
      };
      return (order[a.severity] ?? 5) - (order[b.severity] ?? 5);
    });

    return NextResponse.json(allFindings);
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("GET /api/findings error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// PATCH /api/findings — update triage status
// ---------------------------------------------------------------------------

export async function PATCH(req: NextRequest) {
  try {
    const { userId } = await requireAuth();

    const body: unknown = await req.json();
    if (
      !body ||
      typeof body !== "object" ||
      !("findingId" in body) ||
      !("engagementId" in body) ||
      !("triageStatus" in body)
    ) {
      return NextResponse.json(
        { error: "Missing required fields: findingId, engagementId, triageStatus" },
        { status: 400 },
      );
    }

    const { findingId, engagementId, triageStatus, triageNote } = body as {
      findingId: string;
      engagementId: string;
      triageStatus: string;
      triageNote?: string;
    };

    if (!VALID_TRIAGE_STATUSES.has(triageStatus)) {
      return NextResponse.json(
        { error: `Invalid triage status. Valid: ${[...VALID_TRIAGE_STATUSES].join(", ")}` },
        { status: 400 },
      );
    }

    const engagement = await prisma.engagement.findFirst({
      where: { id: engagementId, userId },
    });
    if (!engagement) {
      return NextResponse.json({ error: "Engagement not found" }, { status: 404 });
    }

    let engDir: string;
    try {
      engDir = resolveEngagementDir(engagement.name, WORKSPACE);
    } catch {
      return NextResponse.json({ error: "Invalid engagement path" }, { status: 400 });
    }

    const state = await loadTriageState(engDir);
    state[findingId] = {
      status: triageStatus as TriageStatus,
      note: typeof triageNote === "string" ? triageNote : undefined,
      updatedAt: new Date().toISOString(),
    };
    await saveTriageState(engDir, state);

    return NextResponse.json({ ok: true, findingId, triageStatus });
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("PATCH /api/findings error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 },
    );
  }
}
