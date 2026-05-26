import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { safeDeleteEngagement } from "@/lib/safe-delete";
import { NextRequest, NextResponse } from "next/server";
import * as path from "path";

const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");

export async function GET(
  _req: NextRequest,
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

    return NextResponse.json(engagement);
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("GET /api/engagements/[id] error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 }
    );
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { userId } = await requireAuth();
    const { id } = await params;
    const body = await req.json();

    const existing = await prisma.engagement.findFirst({
      where: { id, userId },
    });
    if (!existing) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const ALLOWED_FIELDS = ["name", "status", "targetType", "targetValue", "threadId"] as const;
    const data: Record<string, unknown> = {};
    for (const field of ALLOWED_FIELDS) {
      if (field in body) data[field] = body[field];
    }
    if (Object.keys(data).length === 0) {
      return NextResponse.json({ error: "No valid fields to update" }, { status: 400 });
    }

    const engagement = await prisma.engagement.update({
      where: { id },
      data,
    });

    return NextResponse.json(engagement);
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("PATCH /api/engagements/[id] error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { userId } = await requireAuth();
    const { id } = await params;

    const existing = await prisma.engagement.findFirst({
      where: { id, userId },
    });
    if (!existing) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    // Move the workspace directory to Trash (macOS) or `<home>/.trash/` with
    // 30-day retention (other platforms) instead of `rm -rf`-ing it. The DB
    // row is removed only if the filesystem step succeeded, so a hard I/O
    // failure surfaces as a 500 instead of an orphaned workspace.
    try {
      await safeDeleteEngagement(WORKSPACE, existing.name);
    } catch (fsErr) {
      console.error(
        "DELETE /api/engagements/[id] safeDeleteEngagement failed:",
        fsErr,
      );
      return NextResponse.json(
        {
          error:
            "Failed to move engagement workspace to Trash; engagement was not deleted",
        },
        { status: 500 },
      );
    }

    await prisma.engagement.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("DELETE /api/engagements/[id] error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 }
    );
  }
}
