import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { NextRequest, NextResponse } from "next/server";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try { await requireAuth(); } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  await params; // consume params to satisfy Next.js
  const neo4jUri = process.env.NEO4J_URI;
  const neo4jUser = process.env.NEO4J_USER ?? "neo4j";
  const neo4jPassword = process.env.NEO4J_PASSWORD;

  if (!neo4jUri || !neo4jPassword) {
    return NextResponse.json({ nodes: [], edges: [] });
  }

  try {
    // Dynamic import to avoid bundling neo4j-driver when not configured
    const neo4j = await import("neo4j-driver");
    const driver = neo4j.default.driver(
      neo4jUri,
      neo4j.default.auth.basic(neo4jUser, neo4jPassword)
    );

    const session_db = driver.session({ database: "neo4j" });

    try {
      // Fetch all nodes and relationships for visualization
      const result = await session_db.run(`
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
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
        LIMIT 1
      `);

      const record = result.records[0];
      const rawNodes = record?.get("nodes") ?? [];
      const rawEdges = (record?.get("edges") ?? []).filter(Boolean);

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

      // Transform for React Flow
      const nodes = (rawNodes as Neo4jNode[]).map((n, i) => ({
        id: n.id,
        type: "custom",
        data: {
          label: (n.properties.hostname ?? n.properties.ip ?? n.properties.name ?? n.properties.title ?? n.properties.cve_id ?? n.properties.username ?? n.labels[0]) as string,
          nodeType: n.labels[0],
          properties: n.properties,
        },
        position: { x: (i % 6) * 200, y: Math.floor(i / 6) * 150 },
      }));

      const nodeIds = new Set(nodes.map((n) => n.id));
      const edges = (rawEdges as Neo4jEdge[])
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.type,
          data: e.properties,
        }));

      return NextResponse.json({ nodes, edges });
    } finally {
      await session_db.close();
      await driver.close();
    }
  } catch (err: unknown) {
    console.error("Neo4j query error:", err instanceof Error ? err.message : err);
    return NextResponse.json(
      { error: "Knowledge graph unavailable", nodes: [], edges: [] },
      { status: 503 }
    );
  }
}
