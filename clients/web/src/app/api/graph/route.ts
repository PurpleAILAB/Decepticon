import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import neo4j from "neo4j-driver";
import type { Session as Neo4jSession } from "neo4j-driver";
import { NextRequest, NextResponse } from "next/server";

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
// Neo4j → ReactFlow transform
// ---------------------------------------------------------------------------

interface Neo4jNode {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
}

interface Neo4jEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
}

function toReactFlowNodes(raw: Neo4jNode[]) {
  return raw.map((n, i) => ({
    id: n.id,
    type: "custom" as const,
    data: {
      label: String(
        n.properties.hostname ??
          n.properties.ip ??
          n.properties.name ??
          n.properties.title ??
          n.properties.cve_id ??
          n.properties.username ??
          n.labels[0],
      ),
      nodeType: n.labels[0],
      properties: n.properties,
    },
    position: { x: (i % 8) * 200, y: Math.floor(i / 8) * 150 },
  }));
}

function toReactFlowEdges(raw: Neo4jEdge[], validIds: Set<string>) {
  return raw
    .filter((e) => validIds.has(e.source) && validIds.has(e.target))
    .map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.type,
      data: e.properties,
    }));
}

// ---------------------------------------------------------------------------
// GET /api/graph?engagement=…&labels=…&limit=…
// ---------------------------------------------------------------------------

export async function GET(req: NextRequest) {
  try {
    await requireAuth();
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    throw e;
  }

  const cfg = getNeo4jConfig();
  if (!cfg) {
    return NextResponse.json(
      {
        error:
          "Neo4j not configured. Set NEO4J_PASSWORD to a non-default value.",
        nodes: [],
        edges: [],
      },
      { status: 503 },
    );
  }

  const { searchParams } = req.nextUrl;
  const engagement = searchParams.get("engagement");
  const labels = searchParams.get("labels")?.split(",").filter(Boolean) ?? [];
  const limit = Math.min(
    Math.max(Number(searchParams.get("limit")) || 500, 1),
    2000,
  );

  // Build a parameterised Cypher query
  let whereFragments: string[] = [];
  const params: Record<string, unknown> = { limit: neo4j.int(limit) };

  if (engagement) {
    // Validate engagement ownership via Prisma
    const eng = await prisma.engagement.findFirst({
      where: { name: engagement },
    });
    if (!eng) {
      return NextResponse.json({ error: "Engagement not found" }, { status: 404 });
    }
    whereFragments.push("n.engagement = $engagement");
    params.engagement = engagement;
  }
  if (labels.length > 0) {
    // Filter nodes whose first label is in the set
    whereFragments.push(
      "any(l IN labels(n) WHERE l IN $labels)",
    );
    params.labels = labels;
  }

  const whereClause =
    whereFragments.length > 0 ? `WHERE ${whereFragments.join(" AND ")}` : "";

  const cypher = `
    MATCH (n)
    ${whereClause}
    WITH n LIMIT $limit
    OPTIONAL MATCH (n)-[r]->(m)
    ${engagement ? "WHERE m.engagement = $engagement" : ""}
    RETURN
      collect(DISTINCT {
        id: elementId(n),
        labels: labels(n),
        properties: properties(n)
      }) AS nodes,
      collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
        id: elementId(r),
        source: elementId(n),
        target: elementId(m),
        type: type(r),
        properties: properties(r)
      } END) AS edges
  `;

  const driver = neo4j.driver(cfg.uri, neo4j.auth.basic(cfg.user, cfg.password));
  let session: Neo4jSession | null = null;

  try {
    session = driver.session({ database: "neo4j" });
    const result = await session.run(cypher, params);
    const record = result.records[0];
    const rawNodes: Neo4jNode[] = (record?.get("nodes") as Neo4jNode[]) ?? [];
    const rawEdges: Neo4jEdge[] = ((record?.get("edges") as (Neo4jEdge | null)[]) ?? []).filter(
      (e): e is Neo4jEdge => e !== null,
    );

    const nodes = toReactFlowNodes(rawNodes);
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = toReactFlowEdges(rawEdges, nodeIds);

    return NextResponse.json({ nodes, edges });
  } catch (err: unknown) {
    console.error(
      "Neo4j query error:",
      err instanceof Error ? err.message : err,
    );
    return NextResponse.json(
      { error: "Knowledge graph unavailable", nodes: [], edges: [] },
      { status: 503 },
    );
  } finally {
    if (session) await session.close();
    await driver.close();
  }
}
