import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";

const LANGGRAPH_URL = process.env.LANGGRAPH_API_URL ?? "http://langgraph:2024";

interface ThreadInfo {
  thread_id: string;
  created_at: string;
  status: string;
  metadata: Record<string, unknown>;
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { id, userId },
  });
  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Search LangGraph for threads matching this engagement
  try {
    const res = await fetch(`${LANGGRAPH_URL}/threads/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        metadata: { engagement_id: id },
        limit: 20,
      }),
      signal: AbortSignal.timeout(10000),
    });

    if (!res.ok) {
      // Fallback: return just the DB threadId if LangGraph search fails
      if (engagement.threadId) {
        return NextResponse.json([{
          thread_id: engagement.threadId,
          created_at: engagement.updatedAt?.toISOString() ?? "",
          status: "unknown",
          metadata: { engagement_id: id },
        }]);
      }
      return NextResponse.json([]);
    }

    const threads: ThreadInfo[] = await res.json();
    return NextResponse.json(threads);
  } catch {
    // LangGraph unreachable — return DB threadId as fallback
    if (engagement.threadId) {
      return NextResponse.json([{
        thread_id: engagement.threadId,
        created_at: engagement.updatedAt?.toISOString() ?? "",
        status: "stored",
        metadata: { engagement_id: id },
      }]);
    }
    return NextResponse.json([]);
  }
}
