import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { resolveEngagementDir } from "@/lib/workspace";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ParsedFinding {
  title: string;
  severity: string;
  cvssScore?: number;
  affectedAssets: string[];
  mitre: string[];
}

interface FindingDelta {
  title: string;
  severity: string;
  location: "a_only" | "b_only" | "both";
  cvssA?: number;
  cvssB?: number;
}

interface AssetDelta {
  asset: string;
  location: "a_only" | "b_only" | "both";
}

interface MitreDelta {
  techniqueId: string;
  techniqueName: string;
  location: "a_only" | "b_only" | "both";
}

interface DiffStats {
  findingsOnlyA: number;
  findingsOnlyB: number;
  findingsCommon: number;
  assetsOnlyA: number;
  assetsOnlyB: number;
  assetsCommon: number;
  mitreOnlyA: number;
  mitreOnlyB: number;
  mitreCommon: number;
}

interface DiffPayload {
  engagementA: string;
  engagementB: string;
  stats: DiffStats;
  findings: FindingDelta[];
  assets: AssetDelta[];
  mitre: MitreDelta[];
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

const WORKSPACE =
  process.env.WORKSPACE_PATH ??
  path.join(process.env.HOME ?? "", ".decepticon", "workspace");

// ---------------------------------------------------------------------------
// Markdown parser (lightweight, focused on diff-relevant fields)
// ---------------------------------------------------------------------------

function parseFindingMarkdown(content: string, filename: string): ParsedFinding {
  const lines = content.split("\n");
  let title = filename.replace(/\.md$/i, "");
  let severity = "medium";
  let cvssScore: number | undefined;
  const affectedAssets: string[] = [];
  const mitre: string[] = [];
  let currentSection = "";

  for (const line of lines) {
    const h1 = /^#\s+(.+)/.exec(line);
    if (h1) {
      title = h1[1].trim();
      continue;
    }
    const heading = /^##\s+(.+)/.exec(line);
    if (heading) {
      currentSection = heading[1].toLowerCase().trim();
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
        case "mitre":
        case "mitre att&ck":
          mitre.push(...val.split(",").map((m) => m.trim()).filter(Boolean));
          break;
      }
      continue;
    }

    const trimmed = line.trim();
    if (!trimmed) continue;

    // Collect assets
    if (
      currentSection === "affected assets" ||
      currentSection === "assets"
    ) {
      const asset = /^[-*]\s+(.+)/.exec(trimmed);
      if (asset) affectedAssets.push(asset[1].trim());
    }

    // Collect inline MITRE IDs
    const mitreInline = trimmed.match(/\b(T\d{4}(?:\.\d{3})?)\b/g);
    if (mitreInline) {
      for (const tid of mitreInline) {
        if (!mitre.includes(tid)) mitre.push(tid);
      }
    }
  }

  return { title, severity, cvssScore, affectedAssets, mitre };
}

// ---------------------------------------------------------------------------
// Load all findings for an engagement
// ---------------------------------------------------------------------------

async function loadEngagementFindings(
  engagementName: string,
): Promise<ParsedFinding[]> {
  let engDir: string;
  try {
    engDir = resolveEngagementDir(engagementName, WORKSPACE);
  } catch {
    return [];
  }

  const findingsDir = path.join(engDir, "findings");
  let files: string[];
  try {
    files = (await fs.readdir(findingsDir)).filter((f) => f.endsWith(".md"));
  } catch {
    return [];
  }

  const results: ParsedFinding[] = [];
  for (const file of files) {
    try {
      const content = await fs.readFile(path.join(findingsDir, file), "utf-8");
      results.push(parseFindingMarkdown(content, file));
    } catch {
      // Skip malformed
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// Set diff helper
// ---------------------------------------------------------------------------

function setDiff<T>(
  setA: Set<T>,
  setB: Set<T>,
): { onlyA: T[]; onlyB: T[]; common: T[] } {
  const onlyA: T[] = [];
  const onlyB: T[] = [];
  const common: T[] = [];

  for (const item of setA) {
    if (setB.has(item)) common.push(item);
    else onlyA.push(item);
  }
  for (const item of setB) {
    if (!setA.has(item)) onlyB.push(item);
  }

  return { onlyA, onlyB, common };
}

// ---------------------------------------------------------------------------
// GET /api/engagements/diff?a=<id>&b=<id>
// ---------------------------------------------------------------------------

export async function GET(req: NextRequest) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    throw e;
  }

  const aId = req.nextUrl.searchParams.get("a");
  const bId = req.nextUrl.searchParams.get("b");

  if (!aId || !bId) {
    return NextResponse.json(
      { error: "Query params 'a' and 'b' (engagement IDs) are required" },
      { status: 400 },
    );
  }

  if (aId === bId) {
    return NextResponse.json(
      { error: "Cannot diff an engagement against itself" },
      { status: 400 },
    );
  }

  // Validate ownership
  const [engA, engB] = await Promise.all([
    prisma.engagement.findFirst({ where: { id: aId, userId } }),
    prisma.engagement.findFirst({ where: { id: bId, userId } }),
  ]);

  if (!engA) {
    return NextResponse.json({ error: `Engagement A (${aId}) not found` }, { status: 404 });
  }
  if (!engB) {
    return NextResponse.json({ error: `Engagement B (${bId}) not found` }, { status: 404 });
  }

  // Load findings in parallel
  const [findingsA, findingsB] = await Promise.all([
    loadEngagementFindings(engA.name),
    loadEngagementFindings(engB.name),
  ]);

  // --- Findings diff (by title) ---
  const findingsMapA = new Map<string, ParsedFinding>();
  for (const f of findingsA) findingsMapA.set(f.title, f);
  const findingsMapB = new Map<string, ParsedFinding>();
  for (const f of findingsB) findingsMapB.set(f.title, f);

  const findingTitlesA = new Set(findingsMapA.keys());
  const findingTitlesB = new Set(findingsMapB.keys());
  const findingsDiff = setDiff(findingTitlesA, findingTitlesB);

  const findingDeltas: FindingDelta[] = [
    ...findingsDiff.onlyA.map((title): FindingDelta => {
      const f = findingsMapA.get(title)!;
      return { title, severity: f.severity, location: "a_only", cvssA: f.cvssScore };
    }),
    ...findingsDiff.onlyB.map((title): FindingDelta => {
      const f = findingsMapB.get(title)!;
      return { title, severity: f.severity, location: "b_only", cvssB: f.cvssScore };
    }),
    ...findingsDiff.common.map((title): FindingDelta => {
      const a = findingsMapA.get(title)!;
      const b = findingsMapB.get(title)!;
      return {
        title,
        severity: a.severity,
        location: "both",
        cvssA: a.cvssScore,
        cvssB: b.cvssScore,
      };
    }),
  ];

  // --- Assets diff ---
  const assetsA = new Set(findingsA.flatMap((f) => f.affectedAssets));
  const assetsB = new Set(findingsB.flatMap((f) => f.affectedAssets));
  const assetsDiffResult = setDiff(assetsA, assetsB);

  const assetDeltas: AssetDelta[] = [
    ...assetsDiffResult.onlyA.map((asset): AssetDelta => ({ asset, location: "a_only" })),
    ...assetsDiffResult.onlyB.map((asset): AssetDelta => ({ asset, location: "b_only" })),
    ...assetsDiffResult.common.map((asset): AssetDelta => ({ asset, location: "both" })),
  ];

  // --- MITRE diff ---
  const mitreA = new Set(findingsA.flatMap((f) => f.mitre));
  const mitreB = new Set(findingsB.flatMap((f) => f.mitre));
  const mitreDiffResult = setDiff(mitreA, mitreB);

  const mitreDeltas: MitreDelta[] = [
    ...mitreDiffResult.onlyA.map(
      (tid): MitreDelta => ({ techniqueId: tid, techniqueName: tid, location: "a_only" }),
    ),
    ...mitreDiffResult.onlyB.map(
      (tid): MitreDelta => ({ techniqueId: tid, techniqueName: tid, location: "b_only" }),
    ),
    ...mitreDiffResult.common.map(
      (tid): MitreDelta => ({ techniqueId: tid, techniqueName: tid, location: "both" }),
    ),
  ];

  // --- Assemble response ---
  const stats: DiffStats = {
    findingsOnlyA: findingsDiff.onlyA.length,
    findingsOnlyB: findingsDiff.onlyB.length,
    findingsCommon: findingsDiff.common.length,
    assetsOnlyA: assetsDiffResult.onlyA.length,
    assetsOnlyB: assetsDiffResult.onlyB.length,
    assetsCommon: assetsDiffResult.common.length,
    mitreOnlyA: mitreDiffResult.onlyA.length,
    mitreOnlyB: mitreDiffResult.onlyB.length,
    mitreCommon: mitreDiffResult.common.length,
  };

  const payload: DiffPayload = {
    engagementA: engA.name,
    engagementB: engB.name,
    stats,
    findings: findingDeltas,
    assets: assetDeltas,
    mitre: mitreDeltas,
  };

  return NextResponse.json(payload);
}
