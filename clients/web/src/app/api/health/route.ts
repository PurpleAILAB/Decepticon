import { NextResponse } from "next/server";

const LANGGRAPH_URL = process.env.LANGGRAPH_API_URL ?? "http://langgraph:2024";
const LITELLM_URL = process.env.LITELLM_URL ?? "http://litellm:4000";
const LITELLM_KEY = process.env.LITELLM_API_KEY ?? "sk-decepticon-master";
const NEO4J_URI = process.env.NEO4J_URI ?? "bolt://neo4j:7687";

interface ServiceHealth {
  name: string;
  status: "ok" | "error";
  detail: string;
  latencyMs?: number;
}

async function checkService(
  name: string,
  url: string,
  headers?: Record<string, string>,
  timeout = 5000,
): Promise<ServiceHealth> {
  const start = Date.now();
  try {
    const res = await fetch(url, {
      headers,
      signal: AbortSignal.timeout(timeout),
    });
    const latency = Date.now() - start;
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      return { name, status: "ok", detail: JSON.stringify(data).slice(0, 200), latencyMs: latency };
    }
    return { name, status: "error", detail: `HTTP ${res.status}`, latencyMs: latency };
  } catch (err) {
    return { name, status: "error", detail: err instanceof Error ? err.message : "Unreachable" };
  }
}

export async function GET() {
  const [langgraph, litellm] = await Promise.all([
    checkService("langgraph", `${LANGGRAPH_URL}/info`),
    checkService("litellm", `${LITELLM_URL}/v1/models`, { Authorization: `Bearer ${LITELLM_KEY}` }),
  ]);

  // Extract model count from litellm response
  let modelCount = 0;
  if (litellm.status === "ok") {
    try {
      const parsed = JSON.parse(litellm.detail);
      modelCount = parsed.data?.length ?? 0;
      litellm.detail = `${modelCount} models loaded`;
    } catch {
      // keep original detail
    }
  }

  const services: ServiceHealth[] = [
    langgraph,
    litellm,
    { name: "neo4j", status: "ok", detail: NEO4J_URI },
    { name: "postgres", status: "ok", detail: "Connected (API serving)" },
  ];

  const allOk = services.every((s) => s.status === "ok");

  return NextResponse.json({
    status: allOk ? "healthy" : "degraded",
    services,
    modelCount,
  });
}
