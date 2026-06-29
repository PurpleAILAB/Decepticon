import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { resolveEngagementDir } from "@/lib/workspace";
import neo4j from "neo4j-driver";
import type { Session as Neo4jSession } from "neo4j-driver";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TechniqueHit {
  techniqueId: string;
  techniqueName: string;
  tacticId: string;
  count: number;
  engagements: string[];
}

interface MitrePayload {
  techniques: TechniqueHit[];
  totalEngagements: number;
}

// ---------------------------------------------------------------------------
// MITRE ID → tactic mapping (enterprise ATT&CK technique prefixes)
// Techniques belong to ≥1 tactic; we map from the technique node's
// tactic property or infer from the ID range. The Neo4j KG stores
// mitre_technique nodes with `tactic_id` properties when ingested
// by decepticon's research tools. Fallback: filesystem findings that
// list MITRE IDs in their frontmatter.
// ---------------------------------------------------------------------------

const WORKSPACE =
  process.env.WORKSPACE_PATH ??
  path.join(process.env.HOME ?? "", ".decepticon", "workspace");

// ---------------------------------------------------------------------------
// Neo4j connection helpers
// ---------------------------------------------------------------------------

function getNeo4jConfig(): { uri: string; user: string; password: string } | null {
  const password = process.env.NEO4J_PASSWORD;
  if (!password || password === "decepticon-graph") return null;
  return {
    uri: process.env.NEO4J_URI ?? "bolt://neo4j:7687",
    user: process.env.NEO4J_USER ?? "neo4j",
    password,
  };
}

// ---------------------------------------------------------------------------
// Collect MITRE hits from Neo4j
// ---------------------------------------------------------------------------

async function collectFromNeo4j(
  cfg: { uri: string; user: string; password: string },
  engagementFilter?: string,
): Promise<TechniqueHit[]> {
  const driver = neo4j.driver(cfg.uri, neo4j.auth.basic(cfg.user, cfg.password));
  let session: Neo4jSession | null = null;

  try {
    session = driver.session({ database: "neo4j" });

    const whereClause = engagementFilter
      ? "WHERE n.engagement = $engagement"
      : "";
    const params: Record<string, unknown> = engagementFilter
      ? { engagement: engagementFilter }
      : {};

    // Query technique nodes or finding→technique edges
    const cypher = `
      MATCH (n)
      ${whereClause}
      WHERE n.mitre_technique IS NOT NULL OR any(l IN labels(n) WHERE l = 'MitreTechnique')
      RETURN
        COALESCE(n.mitre_technique, n.technique_id, n.name) AS techniqueId,
        COALESCE(n.technique_name, n.name, n.mitre_technique) AS techniqueName,
        COALESCE(n.tactic_id, 'unknown') AS tacticId,
        n.engagement AS engagement,
        count(*) AS hitCount
      ORDER BY hitCount DESC
    `;

    const result = await session.run(cypher, params);
    const hitMap = new Map<string, TechniqueHit>();

    for (const record of result.records) {
      const tid = String(record.get("techniqueId") ?? "");
      if (!tid) continue;

      const existing = hitMap.get(tid);
      const eng = String(record.get("engagement") ?? "unknown");
      const count = typeof record.get("hitCount") === "object"
        ? neo4j.integer.toNumber(record.get("hitCount") as { low: number; high: number })
        : Number(record.get("hitCount"));

      if (existing) {
        existing.count += count;
        if (!existing.engagements.includes(eng)) {
          existing.engagements.push(eng);
        }
      } else {
        hitMap.set(tid, {
          techniqueId: tid,
          techniqueName: String(record.get("techniqueName") ?? tid),
          tacticId: String(record.get("tacticId") ?? "unknown"),
          count,
          engagements: [eng],
        });
      }
    }

    return Array.from(hitMap.values());
  } finally {
    if (session) await session.close();
    await driver.close();
  }
}

// ---------------------------------------------------------------------------
// Fallback: collect from filesystem findings
// ---------------------------------------------------------------------------

async function collectFromFilesystem(
  userId: string,
  engagementFilter?: string,
): Promise<{ techniques: TechniqueHit[]; engagementCount: number }> {
  const engagements = await prisma.engagement.findMany({
    where: engagementFilter
      ? { name: engagementFilter, userId }
      : { userId },
  });

  const hitMap = new Map<string, TechniqueHit>();
  let engCount = 0;

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
      files = (await fs.readdir(findingsDir)).filter((f) => f.endsWith(".md"));
    } catch {
      continue;
    }

    let hasFindings = false;

    for (const file of files) {
      try {
        const content = await fs.readFile(path.join(findingsDir, file), "utf-8");
        const mitreMatches = content.match(/\b(T\d{4}(?:\.\d{3})?)\b/g);
        if (!mitreMatches) continue;
        hasFindings = true;

        // Extract MITRE technique name from context if available
        for (const tid of new Set(mitreMatches)) {
          const existing = hitMap.get(tid);
          // Try to extract technique name from surrounding text
          const nameMatch = new RegExp(
            `${tid.replace(".", "\\.")}[:\\s-]+([^\\n,]+)`,
          ).exec(content);
          const name = nameMatch ? nameMatch[1].trim() : tid;

          if (existing) {
            existing.count++;
            if (!existing.engagements.includes(eng.name)) {
              existing.engagements.push(eng.name);
            }
          } else {
            hitMap.set(tid, {
              techniqueId: tid,
              techniqueName: name,
              tacticId: inferTacticFromTechnique(tid),
              count: 1,
              engagements: [eng.name],
            });
          }
        }
      } catch {
        // Skip
      }
    }

    if (hasFindings) engCount++;
  }

  return { techniques: Array.from(hitMap.values()), engagementCount: engCount };
}

/** Best-effort tactic inference from technique ID for filesystem fallback. */
function inferTacticFromTechnique(tid: string): string {
  // Sub-techniques share parent tactic — strip .NNN suffix
  const parent = tid.split(".")[0];
  // Common technique→tactic mappings for well-known IDs
  const knownMappings: Record<string, string> = {
    T1595: "TA0043", T1592: "TA0043", T1589: "TA0043",
    T1583: "TA0042", T1584: "TA0042", T1588: "TA0042",
    T1190: "TA0001", T1566: "TA0001", T1078: "TA0001",
    T1059: "TA0002", T1053: "TA0002", T1047: "TA0002",
    T1098: "TA0003", T1136: "TA0003", T1543: "TA0003",
    T1548: "TA0004", T1068: "TA0004", T1055: "TA0004",
    T1070: "TA0005", T1036: "TA0005", T1027: "TA0005",
    T1110: "TA0006", T1003: "TA0006", T1552: "TA0006",
    T1083: "TA0007", T1082: "TA0007", T1046: "TA0007",
    T1021: "TA0008", T1570: "TA0008", T1563: "TA0008",
    T1560: "TA0009", T1005: "TA0009", T1074: "TA0009",
    T1071: "TA0011", T1095: "TA0011", T1573: "TA0011",
    T1048: "TA0010", T1041: "TA0010", T1567: "TA0010",
    T1486: "TA0040", T1490: "TA0040", T1498: "TA0040",
  };
  return knownMappings[parent] ?? "unknown";
}

// ---------------------------------------------------------------------------
// GET /api/mitre?engagement=…
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

  const engagement = req.nextUrl.searchParams.get("engagement") ?? undefined;

  // Validate engagement ownership if filtered
  if (engagement) {
    const eng = await prisma.engagement.findFirst({
      where: { name: engagement, userId },
    });
    if (!eng) {
      return NextResponse.json({ error: "Engagement not found" }, { status: 404 });
    }
  }

  const neo4jCfg = getNeo4jConfig();

  // Try Neo4j first, fall back to filesystem
  let techniques: TechniqueHit[] = [];
  let totalEngagements = 0;

  if (neo4jCfg) {
    try {
      techniques = await collectFromNeo4j(neo4jCfg, engagement);
      // Count unique engagements
      const engSet = new Set<string>();
      for (const t of techniques) {
        for (const e of t.engagements) engSet.add(e);
      }
      totalEngagements = engSet.size;
    } catch (err: unknown) {
      console.error(
        "MITRE Neo4j query error, falling back to filesystem:",
        err instanceof Error ? err.message : err,
      );
      // Fall through to filesystem
    }
  }

  // Filesystem fallback or merge
  if (techniques.length === 0) {
    const fsResult = await collectFromFilesystem(userId, engagement);
    techniques = fsResult.techniques;
    totalEngagements = fsResult.engagementCount;
  }

  techniques.sort((a, b) => b.count - a.count);

  const payload: MitrePayload = { techniques, totalEngagements };
  return NextResponse.json(payload);
}
