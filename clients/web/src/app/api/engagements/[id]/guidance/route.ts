import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { resolveEngagementDir } from "@/lib/workspace";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { userId } = await requireAuth();
    const { id } = await params;

    const engagement = await prisma.engagement.findFirst({
      where: { id, userId },
    });

    if (!engagement) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const body = await req.json();
    // Validate type *before* trimming: `body.text?.trim()` throws a TypeError
    // on a non-string (e.g. number) which would surface as a 500 instead of a
    // clean 400, and a post-trim `typeof` check is dead (trim always returns a
    // string).
    const text = typeof body?.text === "string" ? body.text.trim() : "";
    if (!text || text.length > 1000) {
      return NextResponse.json({ error: "Invalid text parameter (max 1000 characters)" }, { status: 400 });
    }

    const engagementDir = resolveEngagementDir(engagement.name, WORKSPACE);
    const guidanceDir = path.join(engagementDir, "guidance");
    const inboxPath = path.join(guidanceDir, "inbox.jsonl");

    await fs.mkdir(guidanceDir, { recursive: true });
    const line = JSON.stringify({ text, timestamp: Date.now() / 1000 }) + "\n";
    await fs.appendFile(inboxPath, line, "utf-8");

    return NextResponse.json({ success: true });
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("POST /api/engagements/[id]/guidance error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 }
    );
  }
}
