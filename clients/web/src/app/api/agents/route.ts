import { NextResponse } from "next/server";
import {
  AGENTS,
  buildAgentConfig,
  type AgentConfig,
} from "@/lib/agents";

const LANGGRAPH_URL =
  process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";

interface LangGraphAssistant {
  assistant_id: string;
  graph_id: string;
  metadata?: Record<string, unknown>;
  name?: string;
}

export async function GET() {
  try {
    const res = await fetch(`${LANGGRAPH_URL}/assistants/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 100 }),
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) {
      return NextResponse.json(AGENTS, {
        headers: { "Cache-Control": "public, s-maxage=10" },
      });
    }

    const assistants: LangGraphAssistant[] = await res.json();

    // Deduplicate by graph_id (LangGraph may return multiple assistants per graph)
    const seen = new Set<string>();
    const agents: AgentConfig[] = [];

    for (const assistant of assistants) {
      const id = assistant.graph_id;
      if (seen.has(id)) continue;
      seen.add(id);
      agents.push(
        buildAgentConfig(id, {
          description:
            (assistant.metadata?.description as string) ?? undefined,
        }),
      );
    }

    return NextResponse.json(agents, {
      headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120" },
    });
  } catch {
    // LangGraph server unreachable — return static fallback
    return NextResponse.json(AGENTS, {
      headers: { "Cache-Control": "public, s-maxage=10" },
    });
  }
}
